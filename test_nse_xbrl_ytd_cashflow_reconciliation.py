import pandas as pd

from nse_xbrl_ytd_cashflow_reconciliation import (
    reconcile_pair,
    select_annual_ytd_pairs,
)


def _filing(symbol, period, pub, description, url):
    return {
        "TckrSymb": symbol,
        "FinancialPeriodEnd": period,
        "PublicationDate": pub,
        "PublicationDateStatus": "VERIFIED",
        "FilingDescription": description,
        "OfficialFilingURL": url,
    }


def _fact(value, *, start, end, basis="STANDALONE", entity="505075", dimensions="[]", unit="iso4217:INR"):
    return {
        "Tag": "CashFlowsFromUsedInOperatingActivities",
        "Value": str(value),
        "StartDate": start,
        "EndDate": end,
        "PeriodClass": "ANNUAL_12M_CANDIDATE" if end == "2026-03-31" else "YTD_9M_CANDIDATE",
        "ReportingBasis": basis,
        "DimensionsJSON": dimensions,
        "UnitMeasure": unit,
        "EntityIdentifier": entity,
        "EntityIdentifierScheme": "http://www.sebi.gov.in/in-capmkt/ScripCode",
        "Namespace": "http://www.sebi.gov.in/xbrl/2026-01-31/in-capmkt",
        "Decimals": "-3",
        "ContextRef": "Annual" if end == "2026-03-31" else "NineMonth",
    }


def _statement(symbol, fact):
    return {"IdentityStatus": "MATCH", "Facts": [fact], "XMLSymbols": [symbol]}


def test_selects_same_basis_nine_month_filing_and_prefers_revision():
    metrics = pd.DataFrame([{
        "TckrSymb": "SETCO", "FinancialPeriodEnd": "2026-03-31",
        "OfficialFilingURL": "https://nsearchives.nseindia.com/annual-setco.xml",
        "MetricCalculationBasis": "LEGACY_CACHE_BASIS_UNKNOWN",
        "OperatingCashFlowINR": 2339411000,
        "Source": "Yahoo Finance via yfinance", "CashFlowPeriodBasis": "UNKNOWN",
    }])
    filings = pd.DataFrame([
        _filing("SETCO", "2026-03-31", "2026-10-23", "Original Standalone Audited", "https://nsearchives.nseindia.com/annual-setco.xml"),
        _filing("SETCO", "2025-12-31", "2026-02-13", "Original Standalone Un-Audited", "https://nsearchives.nseindia.com/9m-setco-original.xml"),
        _filing("SETCO", "2025-12-31", "2026-02-13", "Revision Standalone Un-Audited", "https://nsearchives.nseindia.com/9m-setco-revision.xml"),
        _filing("SETCO", "2025-12-31", "2026-02-13", "Revision Consolidated Un-Audited", "https://nsearchives.nseindia.com/9m-setco-consolidated.xml"),
    ])
    pairs = select_annual_ytd_pairs(metrics, filings, "2026-11-02", limit=5)
    assert len(pairs) == 1
    assert pairs[0]["AnnualReportingBasisExpected"] == "STANDALONE"
    assert pairs[0]["NineMonthFilingURL"].endswith("9m-setco-revision.xml")


def test_derives_q4_cfo_only_as_candidate_when_contexts_match():
    pair = {
        "Symbol": "SETCO", "AnnualReportingBasisExpected": "STANDALONE",
        "NineMonthReportingBasisExpected": "STANDALONE",
        "AnnualPeriodEnd": "2026-03-31", "NineMonthPeriodEnd": "2025-12-31",
        "FiscalStartDate": "2025-04-01",
        "ProviderCFOINR": 2339411000,
        "ProviderCalculationBasis": "LEGACY_CACHE_BASIS_UNKNOWN",
        "ProviderCashFlowPeriodBasis": "UNKNOWN",
    }
    annual = _statement("SETCO", _fact(-5048000, start="2025-04-01", end="2026-03-31"))
    ytd = _statement("SETCO", _fact(12000000, start="2025-04-01", end="2025-12-31"))
    result = reconcile_pair(pair, annual, ytd)
    assert result["Status"] == "DERIVED_Q4_CFO_CANDIDATE_ONLY"
    assert result["DerivedQ4CFOINR"] == "-17048000"
    assert result["VerificationStatus"] == "DERIVED_CANDIDATE_ONLY_NOT_VERIFIED"
    assert result["ProviderComparisonStatus"] == "NOT_COMPARABLE_PROVIDER_BASIS_UNKNOWN"


def test_does_not_derive_when_entity_identity_differs():
    pair = {
        "Symbol": "NIRAJ", "AnnualReportingBasisExpected": "STANDALONE",
        "NineMonthReportingBasisExpected": "STANDALONE",
        "AnnualPeriodEnd": "2026-03-31", "NineMonthPeriodEnd": "2025-12-31",
        "FiscalStartDate": "2025-04-01",
        "AnnualPeriodEnd": "2026-03-31", "NineMonthPeriodEnd": "2025-12-31",
        "FiscalStartDate": "2025-04-01",
    }
    annual = _statement("NIRAJ", _fact(-856518000, start="2025-04-01", end="2026-03-31", entity="532986"))
    ytd = _statement("NIRAJ", _fact(-400000000, start="2025-04-01", end="2025-12-31", entity="OTHER"))
    result = reconcile_pair(pair, annual, ytd)
    assert result["Status"] == "WAIT_FOR_DATA"
    assert "ENTITY_IDENTIFIER_MISMATCH" in result["Reason"]
    assert result["DerivedQ4CFOINR"] is pd.NA or pd.isna(result["DerivedQ4CFOINR"])


def test_does_not_derive_dimensioned_or_wrong_unit_cfo():
    pair = {
        "Symbol": "LAL", "AnnualReportingBasisExpected": "STANDALONE",
        "NineMonthReportingBasisExpected": "STANDALONE",
        "AnnualPeriodEnd": "2026-03-31", "NineMonthPeriodEnd": "2025-12-31",
        "FiscalStartDate": "2025-04-01",
        "AnnualPeriodEnd": "2026-03-31", "NineMonthPeriodEnd": "2025-12-31",
        "FiscalStartDate": "2025-04-01",
    }
    annual = _statement("LAL", _fact(-140004000, start="2025-04-01", end="2026-03-31", dimensions='[{"dimension":"axis"}]'))
    ytd = _statement("LAL", _fact(-90000000, start="2025-04-01", end="2025-12-31", unit="iso4217:USD"))
    result = reconcile_pair(pair, annual, ytd)
    assert result["Status"] == "WAIT_FOR_DATA"
    assert "DIMENSIONED_CFO_FACT_REQUIRES_REVIEW" in result["Reason"]
    assert "UNSUPPORTED_CFO_UNIT" in result["Reason"]


def test_no_pair_when_same_reporting_basis_nine_month_filing_is_absent():
    metrics = pd.DataFrame([{
        "TckrSymb": "DONEAR", "FinancialPeriodEnd": "2026-03-31",
        "OfficialFilingURL": "https://nsearchives.nseindia.com/annual-donear.xml",
        "MetricCalculationBasis": "LEGACY_CACHE_BASIS_UNKNOWN",
        "OperatingCashFlowINR": 156047000,
    }])
    filings = pd.DataFrame([
        _filing("DONEAR", "2026-03-31", "2026-10-13", "Revision Consolidated Audited", "https://nsearchives.nseindia.com/annual-donear.xml"),
        _filing("DONEAR", "2025-12-31", "2026-02-09", "Original Standalone Un-Audited", "https://nsearchives.nseindia.com/9m-donear-standalone.xml"),
    ])
    assert select_annual_ytd_pairs(metrics, filings, "2026-11-02", limit=5) == []
