import pandas as pd

from strategies.ecms.fundamental_research import assess_fundamental_research


def test_strong_available_metrics_get_strong_score_and_separate_verification():
    row = {
        "TckrSymb": "AAA",
        "ProviderSector": "Industrials",
        "RevenueGrowthPct": 30,
        "ProfitGrowthPct": 35,
        "ROEPercent": 24,
        "ROCEPercent": 28,
        "DebtToEquity": 0.2,
        "InterestCoverage": 10,
        "OperatingCashFlowINR": 1000000,
        "FreeCashFlowINR": 500000,
        "TrailingPE": 12,
        "PEG": 0.8,
    }
    verification = pd.DataFrame([{
        "TckrSymb": "AAA",
        "MetricName": "RevenueGrowthPct",
        "MetricValueVerificationStatus": "OFFICIAL_XBRL_VERIFIED",
    }])
    result = assess_fundamental_research(pd.DataFrame([row]), verification).iloc[0]
    assert result["FundamentalResearchClassification"] == "STRONG"
    assert result["FundamentalResearchScore"] >= 75
    assert result["FundamentalResearchCoveragePct"] == 100
    assert result["FundamentalVerificationStatus"] == "PARTIALLY_VERIFIED"
    assert result["FundamentalVerifiedMetricCount"] == 1


def test_missing_metrics_reduce_coverage_instead_of_becoming_zero_score():
    result = assess_fundamental_research(pd.DataFrame([{
        "TckrSymb": "BBB", "ProviderSector": "Industrials",
        "RevenueGrowthPct": 20, "ProfitGrowthPct": 25,
    }])).iloc[0]
    assert result["FundamentalResearchClassification"] == "INSUFFICIENT_DATA"
    assert result["FundamentalResearchCoveragePct"] < 60
    assert pd.isna(result["FundamentalResearchScore"])
    assert result["FundamentalVerificationStatus"] == "NOT_VERIFIED"


def test_weak_complete_metrics_are_classified_weak():
    result = assess_fundamental_research(pd.DataFrame([{
        "TckrSymb": "CCC", "ProviderSector": "Industrials",
        "RevenueGrowthPct": -20, "ProfitGrowthPct": -30,
        "ROEPercent": 1, "ROCEPercent": 2, "DebtToEquity": 4,
        "InterestCoverage": 0.5, "OperatingCashFlowINR": -10,
        "FreeCashFlowINR": -20, "TrailingPE": 80, "PEG": 5,
    }])).iloc[0]
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
