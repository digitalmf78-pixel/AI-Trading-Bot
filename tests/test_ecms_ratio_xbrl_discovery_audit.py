from pathlib import Path

import pandas as pd

from strategies.ecms.ratio_xbrl_discovery_audit import discover_ecms_ratio_xbrl_facts


XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:in-gaap="https://www.nseindia.com/xbrl/ind-as">
  <context id="FY26">
    <entity><identifier scheme="https://www.nseindia.com">INE000A01000</identifier></entity>
    <period><startDate>2025-04-01</startDate><endDate>2026-03-31</endDate></period>
  </context>
  <context id="FY25">
    <entity><identifier scheme="https://www.nseindia.com">INE000A01000</identifier></entity>
    <period><startDate>2024-04-01</startDate><endDate>2025-03-31</endDate></period>
  </context>
  <unit id="pure"><measure>xbrli:pure</measure></unit>
  <in-gaap:ReturnOnEquityRatio contextRef="FY26" unitRef="pure" decimals="2">14.25</in-gaap:ReturnOnEquityRatio>
  <in-gaap:ReturnOnCapitalEmployed contextRef="FY26" unitRef="pure" decimals="2">18.50</in-gaap:ReturnOnCapitalEmployed>
  <in-gaap:InterestServiceCoverageRatio contextRef="FY26" unitRef="pure" decimals="2">3.75</in-gaap:InterestServiceCoverageRatio>
  <in-gaap:RevenueFromOperations contextRef="FY26" unitRef="pure" decimals="2">100</in-gaap:RevenueFromOperations>
  <in-gaap:ReturnOnEquityRatio contextRef="FY25" unitRef="pure" decimals="2">12.00</in-gaap:ReturnOnEquityRatio>
</xbrl>
"""


def _inputs():
    candidates = pd.DataFrame([{
        "TckrSymb": "ABC",
        "FinancialPeriodEnd": "2026-03-31",
    }])
    filings = pd.DataFrame([{
        "TckrSymb": "ABC",
        "FinancialPeriodEnd": "2026-03-31",
        "PublicationDate": "2026-05-20",
        "PublicationDateStatus": "VERIFIED",
        "OfficialFilingURL": "https://nsearchives.nseindia.com/xbrl/ABC.xml",
    }])
    return candidates, filings


def test_discovers_ratio_fact_candidates_but_never_marks_them_verified(tmp_path):
    candidates, filings = _inputs()

    def fake_fetch(_url, destination: Path):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(XML)
        return destination

    result = discover_ecms_ratio_xbrl_facts(
        candidates, filings, tmp_path, fetch_xml=fake_fetch,
    )

    assert set(result["MetricCandidate"]) == {
        "ROEPercent", "ROCEPercent", "InterestCoverage",
    }
    assert set(result["DiscoveryStatus"]) == {"CANDIDATE_FACT_DISCOVERY_ONLY"}
    assert not result["DiscoveryStatus"].astype(str).str.contains("VERIFIED").any()
    assert set(result["PeriodEnd"]) == {"2026-03-31", "2025-03-31"}
    assert result["EvidenceSHA256"].astype(str).str.len().eq(64).all()
    assert result.loc[result["PeriodEnd"].eq("2026-03-31"), "ContextPeriodEndMatchesCandidate"].all()
    assert not result.loc[result["PeriodEnd"].eq("2025-03-31"), "ContextPeriodEndMatchesCandidate"].any()
    assert set(result["ContextPeriodKind"]) == {"DURATION"}
    assert set(result["ContextDimensionStatus"]) == {"UNSEGMENTED"}


def test_rejects_non_official_filing_url_before_fetch(tmp_path):
    candidates, filings = _inputs()
    filings.loc[0, "OfficialFilingURL"] = "https://example.com/ABC.xml"

    def must_not_fetch(*_args):
        raise AssertionError("non-official URL must not be fetched")

    result = discover_ecms_ratio_xbrl_facts(
        candidates, filings, tmp_path, fetch_xml=must_not_fetch,
    )
    assert result.loc[0, "DiscoveryStatus"] == "FILING_URL_NOT_OFFICIAL_OR_MISSING"


def test_requires_unique_exact_symbol_and_period_filing(tmp_path):
    candidates, filings = _inputs()
    filings = pd.concat([filings, filings], ignore_index=True)

    def must_not_fetch(*_args):
        raise AssertionError("ambiguous filing must not be fetched")

    result = discover_ecms_ratio_xbrl_facts(
        candidates, filings, tmp_path, fetch_xml=must_not_fetch,
    )
    assert result.loc[0, "DiscoveryStatus"] == "EXACT_OFFICIAL_FILING_NOT_UNIQUE"
