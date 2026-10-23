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
    assert aaa["PublicationDateStatus"] == "UNVERIFIED"
    assert pd.notna(aaa["DataRetrievedAtUTC"])
    assert aaa["PublicationDateStatus"] == "UNVERIFIED"
    assert pd.notna(aaa["DataRetrievedAtUTC"])
    assert aaa["AsOfDate"] == aaa["FinancialPeriodEnd"]


def test_manual_values_are_not_overwritten(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = Path("data/inputs/fundamental_metrics.csv")
    path.parent.mkdir(parents=True)
    pd.DataFrame([{
        "TckrSymb": "AAA", "AsOfDate": "2026-10-20", "Source": "Manual verified filing",
        "SourceURL": "https://example.com/filing", "RevenueGrowthPct": 77,
    }]).to_csv(path, index=False)
    candidates = pd.DataFrame({"TckrSymb": ["AAA"]})
    result = collect_missing_fundamentals(candidates, metrics_path=path, enabled=True, ticker_factory=FakeTicker, pause_seconds=0)
    aaa = result.set_index("TckrSymb").loc["AAA"]
    assert float(aaa["RevenueGrowthPct"]) == 77
    assert aaa["Source"] == "Manual verified filing"
    assert float(aaa["ROEPercent"]) == 16
    assert aaa["AsOfDate"] == "2026-10-20"


def test_disabled_provider_does_not_drop_candidates_or_call_provider(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    candidates = pd.DataFrame({"TckrSymb": ["AAA", "BBB"]})
    def fail_factory(_):
        raise AssertionError("provider should not be called")
    result = collect_missing_fundamentals(candidates, metrics_path=Path("data/inputs/fundamental_metrics.csv"), enabled=False, ticker_factory=fail_factory, pause_seconds=0)
    assert set(result["TckrSymb"]) == {"AAA", "BBB"}
    diagnostics = pd.read_csv("outputs/v8_fundamental_provider_diagnostics.csv")
    assert set(diagnostics["ProviderStatus"]) == {"DISABLED"}


def test_future_fiscal_year_end_is_not_used_as_financial_period(monkeypatch):
    from fundamental_data_provider import _financial_period_end

    class PeriodTicker:
        financials = pd.DataFrame()

    info = {"nextFiscalYearEnd": 1893456000, "mostRecentQuarter": 1792454400}
    assert _financial_period_end(PeriodTicker(), info) == "2026-10-20"


def test_roe_is_derived_from_statements_when_provider_info_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    class ROEFallbackTicker(FakeTicker):
        def __init__(self, symbol):
            super().__init__(symbol)
            self.info.pop("returnOnEquity", None)
            dates = pd.to_datetime(["2026-03-31", "2025-03-31"])
            self.quarterly_income_stmt = pd.DataFrame(
                [[200, 160]], index=["Net Income"], columns=dates
            )
            self.quarterly_balance_sheet = pd.DataFrame(
                [[1000, 800]], index=["Stockholders Equity"], columns=dates
            )
    result = collect_missing_fundamentals(
        pd.DataFrame({"TckrSymb": ["AAA"]}),
        metrics_path=Path("data/inputs/fundamental_metrics.csv"),
        enabled=True, ticker_factory=ROEFallbackTicker, pause_seconds=0,
        asof_date="2026-03-31",
    )
    row = result.set_index("TckrSymb").loc["AAA"]
    # Net income 200 / average equity ((1000 + 800) / 2) = 11.11%.
    assert round(float(row["ROEPercent"]), 2) == 22.22
    assert str(row["ROECalculationMethod"]).startswith("NET_INCOME_DIVIDED_BY_")


def test_statement_periods_after_eod_are_not_used_for_period_end(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    class FutureStatementTicker(FakeTicker):
        def __init__(self, symbol):
            super().__init__(symbol)
            self.quarterly_income_stmt = pd.DataFrame(
                [[999, 100]], index=["Net Income"],
                columns=pd.to_datetime(["2026-12-31", "2026-03-31"]),
            )
            self.quarterly_balance_sheet = pd.DataFrame(
                [[1000, 800]], index=["Stockholders Equity"],
                columns=pd.to_datetime(["2026-12-31", "2026-03-31"]),
            )
    result = collect_missing_fundamentals(
        pd.DataFrame({"TckrSymb": ["AAA"]}),
        metrics_path=Path("data/inputs/fundamental_metrics.csv"),
        enabled=True, ticker_factory=FutureStatementTicker, pause_seconds=0,
        asof_date="2026-10-22",
    )
    row = result.set_index("TckrSymb").loc["AAA"]
    assert row["FinancialPeriodEnd"] != "2026-12-31"
