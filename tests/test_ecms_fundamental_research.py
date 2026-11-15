import json

import pandas as pd

from strategies.ecms.fundamental_research import assess_fundamental_research


def _with_yahoo_provenance(row):
    metrics = [
        "RevenueGrowthPct", "ProfitGrowthPct", "ROEPercent", "ROCEPercent",
        "DebtToEquity", "InterestCoverage", "OperatingCashFlowINR", "FreeCashFlowINR",
    ]
    row = dict(row)
    row["MetricSourcesJSON"] = json.dumps({m: "Yahoo Finance via yfinance" for m in metrics if m in row})
    row["MetricSourcePeriodsJSON"] = json.dumps({m: "2025-03-31" for m in metrics if m in row})
    row["MetricCalculationBasis"] = "ANNUAL_ALIGNED_STATEMENTS"
    row["MetricPeriodAlignmentStatus"] = "VERIFIED"
    row["ValuationSource"] = "Yahoo Finance via yfinance"
    row["ValuationAsOfDate"] = "2025-03-31"
    return row


def test_strong_available_metrics_get_strong_score_and_separate_verification():
    row = _with_yahoo_provenance({
        "TckrSymb": "AAA", "ProviderSector": "Industrials",
        "RevenueGrowthPct": 30, "ProfitGrowthPct": 35, "ROEPercent": 24,
        "ROCEPercent": 28, "DebtToEquity": 0.2, "InterestCoverage": 10,
        "OperatingCashFlowINR": 1000000, "FreeCashFlowINR": 500000,
        "TrailingPE": 12, "PEG": 0.8,
    })
    verification = pd.DataFrame([{
        "TckrSymb": "AAA", "MetricName": "RevenueGrowthPct",
        "MetricValueVerificationStatus": "OFFICIAL_XBRL_VERIFIED",
    }])
    result = assess_fundamental_research(pd.DataFrame([row]), verification).iloc[0]
    assert result["FundamentalResearchClassification"] == "STRONG"
    assert result["FundamentalResearchScore"] >= 75
    assert result["FundamentalResearchCoveragePct"] == 100
    assert result["FundamentalVerificationStatus"] == "PARTIALLY_VERIFIED"
    assert result["FundamentalVerifiedMetricCount"] == 1
    assert result["FundamentalResearchProvenanceStatus"] == "PROVENANCE_OK"


def test_missing_metrics_reduce_coverage_instead_of_becoming_zero_score():
    row = _with_yahoo_provenance({
        "TckrSymb": "BBB", "ProviderSector": "Industrials",
        "RevenueGrowthPct": 20, "ProfitGrowthPct": 25,
    })
    result = assess_fundamental_research(pd.DataFrame([row])).iloc[0]
    assert result["FundamentalResearchClassification"] == "INSUFFICIENT_DATA"
    assert result["FundamentalResearchCoveragePct"] < 60
    assert pd.isna(result["FundamentalResearchScore"])
    assert result["FundamentalVerificationStatus"] == "NOT_VERIFIED"


def test_weak_complete_metrics_are_classified_weak():
    row = _with_yahoo_provenance({
        "TckrSymb": "CCC", "ProviderSector": "Industrials",
        "RevenueGrowthPct": -20, "ProfitGrowthPct": -30, "ROEPercent": 1,
        "ROCEPercent": 2, "DebtToEquity": 4, "InterestCoverage": 0.5,
        "OperatingCashFlowINR": -10, "FreeCashFlowINR": -20,
        "TrailingPE": 80, "PEG": 5,
    })
    result = assess_fundamental_research(pd.DataFrame([row])).iloc[0]
    assert result["FundamentalResearchClassification"] == "WEAK"
    assert result["FundamentalResearchCoveragePct"] == 100


def test_bank_sector_waits_for_sector_specific_metrics():
    result = assess_fundamental_research(pd.DataFrame([{
        "TckrSymb": "BANK", "ProviderSector": "Banking",
        "RevenueGrowthPct": 30, "ProfitGrowthPct": 35,
        "ROEPercent": 20, "ROCEPercent": 25, "DebtToEquity": 0.2,
        "InterestCoverage": 8, "OperatingCashFlowINR": 100,
    }])).iloc[0]
    assert result["FundamentalResearchClassification"] == "INSUFFICIENT_DATA"
    assert pd.isna(result["FundamentalResearchScore"])
    assert "SECTOR_SPECIFIC_RULES_REQUIRED" in result["FundamentalResearchNotes"]


def test_legacy_or_unaligned_metrics_are_not_scored_without_metric_provenance():
    result = assess_fundamental_research(pd.DataFrame([{
        "TckrSymb": "OLD", "ProviderSector": "Industrials",
        "RevenueGrowthPct": 40, "ProfitGrowthPct": 45,
        "TrailingPE": 10, "PEG": 0.5,
    }])).iloc[0]
    assert result["FundamentalResearchCoveragePct"] == 0
    assert result["FundamentalResearchClassification"] == "INSUFFICIENT_DATA"
    assert "PROVENANCE_BLOCKED" in result["FundamentalResearchNotes"]


def test_mixed_source_metrics_need_a_valid_period_and_metric_level_basis():
    row = {
        "TckrSymb": "MIX", "ProviderSector": "Industrials",
        "RevenueGrowthPct": 20, "ProfitGrowthPct": 25,
        "MetricSourcesJSON": json.dumps({
            "RevenueGrowthPct": "Moneycontrol", "ProfitGrowthPct": "Tickertape",
        }),
        "MetricSourcePeriodsJSON": json.dumps({
            "RevenueGrowthPct": "2025-03-31", "ProfitGrowthPct": "",
        }),
        "MetricCalculationBasis": "MULTI_SOURCE_METRIC_LEVEL",
        "MetricPeriodAlignmentStatus": "UNVERIFIED",
    }
    result = assess_fundamental_research(pd.DataFrame([row])).iloc[0]
    assert result["FundamentalResearchEligibleMetricCount"] == 1
    assert "ProfitGrowthPct:PERIOD_MISSING_OR_INVALID" in result["FundamentalResearchNotes"]

def test_mixed_yahoo_and_free_source_metrics_use_independent_calculation_bases():
    row = {
        "TckrSymb": "MIXED", "ProviderSector": "Industrials",
        "RevenueGrowthPct": 20, "ProfitGrowthPct": 25,
        "MetricSourcesJSON": json.dumps({
            "RevenueGrowthPct": "Yahoo Finance via yfinance",
            "ProfitGrowthPct": "Moneycontrol",
        }),
        "MetricSourcePeriodsJSON": json.dumps({
            "RevenueGrowthPct": "2025-03-31",
            "ProfitGrowthPct": "FY2024->FY2025",
        }),
        "MetricCalculationBasis": "ANNUAL_ALIGNED_STATEMENTS",
        "MetricPeriodAlignmentStatus": "VERIFIED",
        "MetricCalculationBasesJSON": json.dumps({
            "RevenueGrowthPct": "ANNUAL_ALIGNED_STATEMENTS",
            "ProfitGrowthPct": "MULTI_SOURCE_METRIC_LEVEL",
        }),
    }
    result = assess_fundamental_research(pd.DataFrame([row])).iloc[0]
    assert result["FundamentalResearchEligibleMetricCount"] == 2
    assert "PROVENANCE_BLOCKED" not in result["FundamentalResearchNotes"]


def test_free_source_fiscal_growth_period_must_be_consecutive_and_not_latest_label():
    row = {
        "TckrSymb": "PERIOD", "ProviderSector": "Industrials",
        "RevenueGrowthPct": 20, "ProfitGrowthPct": 25,
        "ROEPercent": 15,
        "MetricSourcesJSON": json.dumps({
            "RevenueGrowthPct": "Moneycontrol",
            "ProfitGrowthPct": "Tickertape",
            "ROEPercent": "Moneycontrol",
        }),
        "MetricSourcePeriodsJSON": json.dumps({
            "RevenueGrowthPct": "FY2024->FY2026",
            "ProfitGrowthPct": "FY2024->FY2025",
            "ROEPercent": "Latest",
        }),
        "MetricCalculationBasis": "ANNUAL_ALIGNED_STATEMENTS",
        "MetricPeriodAlignmentStatus": "VERIFIED",
        "MetricCalculationBasesJSON": json.dumps({
            "RevenueGrowthPct": "MULTI_SOURCE_METRIC_LEVEL",
            "ProfitGrowthPct": "MULTI_SOURCE_METRIC_LEVEL",
            "ROEPercent": "MULTI_SOURCE_METRIC_LEVEL",
        }),
    }
    result = assess_fundamental_research(pd.DataFrame([row])).iloc[0]
    assert result["FundamentalResearchEligibleMetricCount"] == 1
    assert "RevenueGrowthPct:PERIOD_MISSING_OR_INVALID" in result["FundamentalResearchNotes"]
    assert "ROEPercent:PERIOD_MISSING_OR_INVALID" in result["FundamentalResearchNotes"]

