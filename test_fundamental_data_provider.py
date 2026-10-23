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
