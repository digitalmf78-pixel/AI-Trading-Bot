import pandas as pd
import pytest

from strategies.ecms.fundamental_source_compilation import (
    MANUAL_COLUMNS,
    build_fundamental_source_compilation,
    empty_manual_observation_template,
)


def test_compilation_ignores_screener_as_fundamental_provider():
    metrics = pd.DataFrame([{
        "TckrSymb": "AAA", "ROEPercent": 18.0,
        "MetricSourcesJSON": '{"ROEPercent":"Yahoo Finance via yfinance"}',
        "MetricSourceURLsJSON": '{"ROEPercent":"https://finance.yahoo.com/quote/AAA.NS/"}',
        "MetricSourcePeriodsJSON": '{"ROEPercent":"Mar 2026"}',
        "MetricCalculationBasesJSON": '{"ROEPercent":"ANNUAL_ALIGNED_STATEMENTS"}',
        "MetricSourceCurrenciesJSON": '{"ROEPercent":"PERCENT"}',
    }])
    manual = pd.DataFrame([{
        "TckrSymb": "AAA", "MetricName": "ROEPercent", "MetricValue": 17.5,
        "Source": "SCREENER_FREE_MANUAL", "SourceURL": "https://www.screener.in/company/AAA/",
        "FinancialPeriodEnd": "2026-03-31", "PublicationDate": "2026-05-10",
        "CalculationBasis": "CONSOLIDATED", "Unit": "PERCENT",
        "ObservationNotes": "Must not be used as an alternate provider",
    }], columns=MANUAL_COLUMNS)

    result = build_fundamental_source_compilation(metrics, manual_observations=manual)
    assert result["Source"].tolist() == ["Yahoo Finance via yfinance"]


def test_compilation_includes_only_yahoo_metric_values():
    metrics = pd.DataFrame([{
        "TckrSymb": "AAA", "ROEPercent": 18.0, "ROCEPercent": 21.0,
        "MetricSourcesJSON": '{"ROEPercent":"Yahoo Finance via yfinance","ROCEPercent":"Other Provider"}',
        "MetricSourcePeriodsJSON": '{"ROEPercent":"Mar 2026","ROCEPercent":"Mar 2026"}',
        "MetricCalculationBasesJSON": '{"ROEPercent":"ANNUAL_ALIGNED_STATEMENTS","ROCEPercent":"ANNUAL_ALIGNED_STATEMENTS"}',
        "MetricSourceCurrenciesJSON": '{"ROEPercent":"PERCENT","ROCEPercent":"PERCENT"}',
    }])
    result = build_fundamental_source_compilation(metrics)
    assert result["MetricName"].tolist() == ["ROEPercent"]
    assert result.iloc[0]["Source"] == "Yahoo Finance via yfinance"


def test_compilation_carries_official_nse_verification_without_upgrading_manual_source():
    metrics = pd.DataFrame([{"TckrSymb": "AAA", "DebtToEquity": 0.5}])
    verification = pd.DataFrame([{
        "TckrSymb": "AAA", "MetricName": "DebtToEquity",
        "MetricValueVerificationStatus": "OFFICIAL_XBRL_VERIFIED",
        "OfficialMetricValue": 0.5, "VerificationMethod": "NSE_XBRL",
    }])
    manual = pd.DataFrame([{
        "TckrSymb": "AAA", "MetricName": "DebtToEquity", "MetricValue": 0.6,
        "Source": "BSE_OFFICIAL_FILING_MANUAL", "SourceURL": "https://www.bseindia.com/",
        "FinancialPeriodEnd": "2026-03-31", "PublicationDate": "2026-05-10",
        "CalculationBasis": "STANDALONE", "Unit": "RATIO", "ObservationNotes": "",
    }], columns=MANUAL_COLUMNS)

    result = build_fundamental_source_compilation(metrics, verification, manual)
    official = result[result["Source"] == "NSE_OFFICIAL_XBRL_AUDIT"].iloc[0]
    bse = result[result["Source"] == "BSE_OFFICIAL_FILING_VERIFICATION_EVIDENCE"].iloc[0]

    assert official["VerificationStatus"] == "OFFICIAL_XBRL_VERIFIED"
    assert bse["VerificationStatus"] == "MANUAL_REVIEW_REQUIRED"
    assert bse["SourceStatus"] == "OFFICIAL_VERIFICATION_EVIDENCE_PENDING"
    assert bse["MetricValue"] == 0.6


def test_manual_source_ignores_unknown_or_premium_scrape_source():
    manual = pd.DataFrame([{
        "TckrSymb": "AAA", "MetricName": "ROEPercent", "MetricValue": 10,
        "Source": "SCREENER_PREMIUM_SCRAPE", "SourceURL": "", "FinancialPeriodEnd": "",
        "PublicationDate": "", "CalculationBasis": "", "Unit": "", "ObservationNotes": "",
    }], columns=MANUAL_COLUMNS)
    result = build_fundamental_source_compilation(
        pd.DataFrame([{"TckrSymb": "AAA"}]), manual_observations=manual
    )
    assert result.empty


def test_empty_manual_template_has_only_expected_columns():
    assert list(empty_manual_observation_template().columns) == MANUAL_COLUMNS


def test_compilation_includes_exact_debt_equity_audit_as_its_own_source_row():
    metrics = pd.DataFrame([{"TckrSymb": "AAA", "DebtToEquity": 0.5}])
    debt_audit = pd.DataFrame([{
        "TckrSymb": "AAA", "DebtToEquityAuditStatus": "OFFICIAL_XBRL_VERIFIED",
        "OfficialDebtToEquity": 0.5, "FinancialPeriodEnd": "2026-03-31",
        "ReportingBasis": "STANDALONE", "DebtToEquityAuditReason": "Exact same-context match",
    }])
    result = build_fundamental_source_compilation(metrics, debt_equity_audit=debt_audit)
    audit = result[result["Source"] == "NSE_OFFICIAL_XBRL_DEBT_EQUITY_AUDIT"].iloc[0]
    assert audit["VerificationStatus"] == "OFFICIAL_XBRL_VERIFIED"
    assert audit["MetricValue"] == 0.5


def test_compilation_flags_mismatch_only_when_period_basis_and_unit_align():
    metrics = pd.DataFrame([{
        "TckrSymb": "AAA", "ROEPercent": 18.0,
        "MetricSourcesJSON": '{"ROEPercent":"Yahoo Finance via yfinance"}',
        "MetricSourcePeriodsJSON": '{"ROEPercent":"2026-03-31"}',
        "MetricCalculationBasesJSON": '{"ROEPercent":"CONSOLIDATED"}',
        "MetricSourceCurrenciesJSON": '{"ROEPercent":"PERCENT"}',
    }])
    manual = pd.DataFrame([{
        "TckrSymb": "AAA", "MetricName": "ROEPercent", "MetricValue": 15.0,
        "Source": "BSE_OFFICIAL_FILING_MANUAL", "SourceURL": "https://www.bseindia.com/",
        "FinancialPeriodEnd": "2026-03-31", "PublicationDate": "2026-05-10",
        "CalculationBasis": "CONSOLIDATED", "Unit": "PERCENT", "ObservationNotes": "",
    }], columns=MANUAL_COLUMNS)
    result = build_fundamental_source_compilation(metrics, manual_observations=manual)
    assert result["MismatchStatus"].eq("MISMATCH").all()
    assert result["MismatchReason"].str.contains("comparison tolerance").all()



def test_verification_audit_does_not_label_mismatching_cached_value_as_official_fact():
    metrics = pd.DataFrame([{"TckrSymb": "AAA", "ROEPercent": 18.0}])
    verification = pd.DataFrame([
        {
            "TckrSymb": "AAA", "MetricName": "ROEPercent",
            "CachedMetricValue": 18.0,
            "MetricValueVerificationStatus": "PROVIDER_VALUE_MISMATCH",
            "MetricValueVerificationReason": "Provider growth differs from official calculation",
            "FinancialPeriodEnd": "2026-03-31",
            "OfficialFilingURL": "https://nsearchives.nseindia.com/example.xml",
        },
        {
            "TckrSymb": "AAA", "MetricName": "RevenueGrowthPct",
            "CachedMetricValue": 12.0,
            "MetricValueVerificationStatus": "OFFICIAL_XBRL_VERIFIED",
            "MetricValueVerificationReason": "Exact verified value",
            "FinancialPeriodEnd": "2026-03-31",
            "OfficialFilingURL": "https://nsearchives.nseindia.com/example.xml",
        },
    ])
    result = build_fundamental_source_compilation(metrics, verification)
    audit = result[result["Source"] == "NSE_OFFICIAL_XBRL_AUDIT"].set_index("MetricName")

    assert pd.isna(audit.loc["ROEPercent", "MetricValue"])
    assert audit.loc["ROEPercent", "VerificationStatus"] == "PROVIDER_VALUE_MISMATCH"
    assert audit.loc["ROEPercent", "MismatchReason"] == "Provider growth differs from official calculation"
    assert audit.loc["RevenueGrowthPct", "MetricValue"] == 12.0
    assert audit.loc["RevenueGrowthPct", "VerificationStatus"] == "OFFICIAL_XBRL_VERIFIED"
