from pathlib import Path

import pandas as pd

from strategies.ecms.debt_equity_xbrl_audit import audit_ecms_debt_to_equity


URL = "https://nsearchives.nseindia.in/corporate/xbrl/AAA.xml"


def _xml(report_basis="Standalone", split_components=False):
    instant_a = """<xbrli:context id="instantA"><xbrli:entity><xbrli:identifier scheme="https://www.nseindia.com">INE000A01000</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-03-31</xbrli:instant></xbrli:period></xbrli:context>"""
    instant_b = """<xbrli:context id="instantB"><xbrli:entity><xbrli:identifier scheme="https://www.nseindia.com">INE000A01000</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-03-31</xbrli:instant></xbrli:period></xbrli:context>"""
    duration = """<xbrli:context id="annual"><xbrli:entity><xbrli:identifier scheme="https://www.nseindia.com">INE000A01000</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2025-04-01</xbrli:startDate><xbrli:endDate>2026-03-31</xbrli:endDate></xbrli:period></xbrli:context>"""
    equity_context = "instantB" if split_components else "instantA"
    total_equity = "100" if report_basis == "Standalone" else "110"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
    <xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:in="urn:test:in-gaap">
      {instant_a}{instant_b}{duration}
      <xbrli:unit id="INR"><xbrli:measure>INR</xbrli:measure></xbrli:unit>
      <in:NatureOfReportStandaloneConsolidated contextRef="annual"> {report_basis} </in:NatureOfReportStandaloneConsolidated>
      <in:BorrowingsCurrent contextRef="instantA" unitRef="INR" decimals="INF">20</in:BorrowingsCurrent>
      <in:BorrowingsNoncurrent contextRef="instantA" unitRef="INR" decimals="INF">30</in:BorrowingsNoncurrent>
      <in:Equity contextRef="{equity_context}" unitRef="INR" decimals="INF">{total_equity}</in:Equity>
      <in:EquityAttributableToOwnersOfParent contextRef="{equity_context}" unitRef="INR" decimals="INF">100</in:EquityAttributableToOwnersOfParent>
    </xbrli:xbrl>"""


def _inputs(provider_ratio=0.5, sector="Industrials", filing_basis="Standalone"):
    metrics = pd.DataFrame([{
        "TckrSymb": "AAA",
        "DebtToEquity": provider_ratio,
        "ProviderSector": sector,
        "FinancialPeriodEnd": "2026-03-31",
        "PublicationDate": "2026-05-20",
        "PublicationDateStatus": "VERIFIED",
        "MetricCalculationBasis": "ANNUAL_ALIGNED_STATEMENTS",
        "OfficialFilingURL": URL,
        "MetricSourcesJSON": '{"DebtToEquity":"Yahoo Finance via yfinance"}',
    }])
    filings = pd.DataFrame([{
        "TckrSymb": "AAA",
        "FinancialPeriodEnd": "2026-03-31",
        "PublicationDate": "2026-05-20",
        "PublicationDateStatus": "VERIFIED",
        "OfficialFilingURL": URL,
        "FilingDescription": f"Annual Financial Results - {filing_basis}",
    }])
    return metrics, filings


def _run(tmp_path, xml, provider_ratio=0.5, sector="Industrials", filing_basis="Standalone"):
    metrics, filings = _inputs(provider_ratio, sector, filing_basis)

    def fetcher(url, destination):
        assert url == URL
        Path(destination).write_text(xml, encoding="utf-8")

    return audit_ecms_debt_to_equity(
        metrics, filings, tmp_path, fetch_xml=fetcher
    ).iloc[0]


def test_standalone_ratio_is_recomputed_from_same_instant_context(tmp_path):
    row = _run(tmp_path, _xml())

    assert row["DebtToEquityAuditStatus"] == "OFFICIAL_XBRL_VERIFIED"
    assert row["OfficialDebtToEquity"] == 0.5
    assert row["BorrowingsCurrentINR"] == 20
    assert row["BorrowingsNoncurrentINR"] == 30
    assert row["EquityINR"] == 100
    assert row["EquityFactTag"] == "Equity"
    assert row["ReportingBasis"] == "STANDALONE"
    assert len(row["EvidenceSHA256"]) == 64


def test_provider_mismatch_is_not_upgraded_to_verified(tmp_path):
    row = _run(tmp_path, _xml(), provider_ratio=0.6)

    assert row["DebtToEquityAuditStatus"] == "PROVIDER_VALUE_MISMATCH"
    assert row["OfficialDebtToEquity"] == 0.5


def test_consolidated_basis_uses_total_equity_not_parent_only_equity(tmp_path):
    row = _run(
        tmp_path, _xml(report_basis="Consolidated"),
        filing_basis="Consolidated",
    )

    assert row["DebtToEquityAuditStatus"] == "PROVIDER_VALUE_MISMATCH"
    assert row["OfficialDebtToEquity"] == 50 / 110
    assert row["EquityINR"] == 110
    assert row["EquityFactTag"] == "Equity"


def test_xbrl_reporting_basis_must_match_official_filing_description(tmp_path):
    row = _run(
        tmp_path, _xml(report_basis="Consolidated"),
        filing_basis="Standalone",
    )

    assert row["DebtToEquityAuditStatus"] == "XBRL_COMPONENTS_UNRESOLVED"
    assert "conflicts with filing register" in row["DebtToEquityAuditReason"]


def test_components_from_different_instant_contexts_are_rejected(tmp_path):
    row = _run(tmp_path, _xml(split_components=True))

    assert row["DebtToEquityAuditStatus"] == "XBRL_COMPONENTS_UNRESOLVED"
    assert "same-context" in row["DebtToEquityAuditReason"]


def test_financial_sector_is_not_scored_with_industrial_ratio(tmp_path):
    row = _run(tmp_path, _xml(), sector="Financial Services")

    assert row["DebtToEquityAuditStatus"] == "NOT_APPLICABLE_FINANCIAL_SECTOR"
    assert pd.isna(row["OfficialDebtToEquity"])


def test_missing_source_provenance_fails_closed(tmp_path):
    metrics, filings = _inputs()
    metrics.loc[0, "MetricSourcesJSON"] = "{}"
    result = audit_ecms_debt_to_equity(
        metrics, filings, tmp_path,
        fetch_xml=lambda _url, _path: (_ for _ in ()).throw(AssertionError("must not fetch")),
    )

    assert result.iloc[0]["DebtToEquityAuditStatus"] == "PROVIDER_SOURCE_NOT_APPROVED"



def test_missing_provider_metric_is_reported_not_silently_dropped(tmp_path):
    metrics, filings = _inputs()
    metrics.loc[0, "DebtToEquity"] = ""
    result = audit_ecms_debt_to_equity(
        metrics, filings, tmp_path,
        fetch_xml=lambda _url, _path: (_ for _ in ()).throw(AssertionError("must not fetch")),
    )

    assert len(result) == 1
    assert result.iloc[0]["DebtToEquityAuditStatus"] == "PROVIDER_METRIC_MISSING"
