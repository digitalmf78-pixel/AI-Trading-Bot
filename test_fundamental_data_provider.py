import os
import tempfile
from pathlib import Path

import pandas as pd

from fundamental_data_provider import collect_missing_fundamentals


class FakeTicker:
    def __init__(self, symbol):
        self.symbol = symbol
        self.info = {
            "revenueGrowth": 0.12,
            "earningsGrowth": 0.18,
            "returnOnEquity": 0.16,
            "debtToEquity": 45.0,
            "operatingCashflow": 1000,
            "freeCashflow": 600,
            "ebit": 800,
            "interestExpense": 100,
            "totalAssets": 5000,
            "totalCurrentLiabilities": 1000,
            "totalDebt": 900,
            "totalStockholderEquity": 2000,
            "trailingPE": 20,
            "mostRecentQuarter": 1792454400,
        }
        self.financials = pd.DataFrame()
        self.balance_sheet = pd.DataFrame()
        self.cashflow = pd.DataFrame()


def test_fetches_each_unique_delivery_candidate_and_writes_diagnostics(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    candidates = pd.DataFrame({"TckrSymb": ["AAA", "BBB", "AAA"]})
    result = collect_missing_fundamentals(
        candidates,
        metrics_path=Path("data/inputs/fundamental_metrics.csv"),
        enabled=True,
        ticker_factory=FakeTicker,
        pause_seconds=0,
        asof_date="2026-10-22",
        filings_fetcher=lambda _cutoff: pd.DataFrame(),
    )
    assert set(result["TckrSymb"]) == {"AAA", "BBB"}
    assert len(pd.read_csv("outputs/v8_fundamental_provider_diagnostics.csv")) == 2
    aaa = result.set_index("TckrSymb").loc["AAA"]
    assert round(float(aaa["RevenueGrowthPct"]), 2) == 12.0
    assert round(float(aaa["ProfitGrowthPct"]), 2) == 18.0
    assert round(float(aaa["ROEPercent"]), 2) == 16.0
    assert round(float(aaa["DebtToEquity"]), 2) == 0.45
    assert round(float(aaa["ROCEPercent"]), 2) == 20.0
    assert round(float(aaa["InterestCoverage"]), 2) == 8.0


def test_manual_values_are_not_overwritten(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = Path("data/inputs/fundamental_metrics.csv")
    path.parent.mkdir(parents=True)
    pd.DataFrame([{
        "TckrSymb": "AAA", "AsOfDate": "2026-10-20", "Source": "Manual verified filing",
        "SourceURL": "https://example.com/filing", "RevenueGrowthPct": 77,
    }]).to_csv(path, index=False)
    candidates = pd.DataFrame({"TckrSymb": ["AAA"]})
    result = collect_missing_fundamentals(candidates, metrics_path=path, enabled=True, ticker_factory=FakeTicker, pause_seconds=0, asof_date="2026-10-22", filings_fetcher=lambda _cutoff: pd.DataFrame())
    aaa = result.set_index("TckrSymb").loc["AAA"]
    assert float(aaa["RevenueGrowthPct"]) == 77
    assert aaa["Source"] == "Manual verified filing"
    assert float(aaa["ROEPercent"]) == 16


def test_disabled_provider_does_not_drop_candidates_or_call_provider(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    candidates = pd.DataFrame({"TckrSymb": ["AAA", "BBB"]})
    def fail_factory(_):
        raise AssertionError("provider should not be called")
    result = collect_missing_fundamentals(candidates, metrics_path=Path("data/inputs/fundamental_metrics.csv"), enabled=False, ticker_factory=fail_factory, pause_seconds=0, asof_date="2026-10-22", filings_fetcher=lambda _cutoff: pd.DataFrame())
    assert set(result["TckrSymb"]) == {"AAA", "BBB"}
    diagnostics = pd.read_csv("outputs/v8_fundamental_provider_diagnostics.csv")
    assert set(diagnostics["ProviderStatus"]) == {"DISABLED"}


def test_asof_date_and_retrieval_timestamp_are_separate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = collect_missing_fundamentals(
        pd.DataFrame({"TckrSymb": ["AAA"]}),
        metrics_path=Path("data/inputs/fundamental_metrics.csv"), enabled=True,
        ticker_factory=FakeTicker, pause_seconds=0, asof_date="2026-10-22",
        filings_fetcher=lambda _cutoff: pd.DataFrame(),
    )
    row = result.set_index("TckrSymb").loc["AAA"]
    assert str(row["AsOfDate"])[:10] == "2026-10-22"
    assert "T" in str(row["DataRetrievedAtUTC"])
    assert row["PublicationDateStatus"] == "UNVERIFIED"


def test_provider_diagnostics_expose_unaligned_snapshot_basis():
    from fundamental_data_provider import _fetch_one
    record, diagnostic = _fetch_one("AAA", ticker_factory=FakeTicker)
    assert diagnostic["MetricCalculationBasis"] == "UNALIGNED_PROVIDER_SNAPSHOT"
    assert diagnostic["QuarterlyAlignmentStatus"] == "NOT_ALIGNED"
    assert diagnostic["QuarterlyAlignmentReason"]
    assert record["MetricCalculationBasis"] == "UNALIGNED_PROVIDER_SNAPSHOT"
    assert record["MetricPeriodAlignmentStatus"] == "UNVERIFIED"


def test_provider_diagnostics_expose_quarterly_ttm_basis():
    from fundamental_data_provider import _fetch_one

    class QuarterlyTicker(FakeTicker):
        def __init__(self, symbol):
            super().__init__(symbol)
            cols = pd.to_datetime(["2026-09-30", "2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30"])
            self.quarterly_financials = pd.DataFrame({c: [100, 20, 25, 5] for c in cols}, index=["Total Revenue", "Net Income", "EBIT", "Interest Expense"])
            q4 = cols[:4]
            self.quarterly_cashflow = pd.DataFrame({c: [10, -2, 8] for c in q4}, index=["Operating Cash Flow", "Capital Expenditure", "Free Cash Flow"])
            self.quarterly_balance_sheet = pd.DataFrame({c: [1000, 200, 500, 300] for c in cols[:2]}, index=["Total Assets", "Current Liabilities", "Stockholders Equity", "Total Debt"])

    record, diagnostic = _fetch_one("AAA", ticker_factory=QuarterlyTicker)
    assert diagnostic["MetricCalculationBasis"] == "QUARTERLY_YOY_TTM"
    assert diagnostic["QuarterlyAlignmentStatus"] == "VERIFIED"
    assert record["MetricCalculationBasis"] == "QUARTERLY_YOY_TTM"
    assert record["MetricPeriodAlignmentStatus"] == "VERIFIED"


def test_legacy_cache_basis_is_migrated_to_unknown_without_changing_metrics(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = Path("data/inputs/fundamental_metrics.csv")
    path.parent.mkdir(parents=True)
    original = pd.DataFrame([{
        "TckrSymb": "LEGACY", "AsOfDate": "2026-10-28",
        "FinancialPeriodEnd": "2026-03-31", "MetricPeriodAlignmentStatus": "VERIFIED",
        "RevenueGrowthPct": 12.5, "ROEPercent": 14.2,
    }])
    original.to_csv(path, index=False)
    result = collect_missing_fundamentals(
        pd.DataFrame({"TckrSymb": ["LEGACY"]}), metrics_path=path, enabled=False,
        pause_seconds=0, asof_date="2026-10-29",
    )
    row = result.set_index("TckrSymb").loc["LEGACY"]
    assert row["MetricCalculationBasis"] == "LEGACY_CACHE_BASIS_UNKNOWN"
    assert "predates calculation-basis tracking" in row["QuarterlyAlignmentReason"]
    assert float(row["RevenueGrowthPct"]) == 12.5
    assert float(row["ROEPercent"]) == 14.2
    # Historical alignment flags are not promoted or rewritten by this migration.
    assert row["MetricPeriodAlignmentStatus"] == "VERIFIED"
    persisted = pd.read_csv(path).set_index("TckrSymb").loc["LEGACY"]
    assert persisted["MetricCalculationBasis"] == "LEGACY_CACHE_BASIS_UNKNOWN"


def test_existing_unknown_basis_is_not_mislabeled_as_quarterly(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = Path("data/inputs/fundamental_metrics.csv")
    path.parent.mkdir(parents=True)
    pd.DataFrame([{
        "TckrSymb": "UNKNOWN", "MetricCalculationBasis": "",
        "RevenueGrowthPct": 1.0,
    }]).to_csv(path, index=False)
    result = collect_missing_fundamentals(
        pd.DataFrame({"TckrSymb": ["UNKNOWN"]}), metrics_path=path, enabled=False,
        pause_seconds=0, asof_date="2026-10-29",
    )
    row = result.set_index("TckrSymb").loc["UNKNOWN"]
    assert row["MetricCalculationBasis"] == "LEGACY_CACHE_BASIS_UNKNOWN"
    assert row["MetricCalculationBasis"] != "QUARTERLY_YOY_TTM"
