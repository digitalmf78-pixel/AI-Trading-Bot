import pytest

from upstox_fundamentals import fetch_upstox_fundamentals, metrics_from_responses
from fundamental_data_provider import _apply_upstox_fallback


def _responses(balance_period="Mar 2025"):
    return (
        {"status": "success", "data": {"type": "consolidated", "time_period": "yearly", "units_in": "crore",
            "income_statement": [
                {"category": "revenue", "history": [{"period": "Mar 2025", "value": 120}, {"period": "Mar 2024", "value": 100}]},
                {"category": "net_profit", "history": [{"period": "Mar 2025", "value": 24}, {"period": "Mar 2024", "value": 20}]},
            ]}},
        {"status": "success", "data": {"type": "consolidated", "time_period": "yearly", "units_in": "crore",
            "history": [{"period": balance_period, "total_asset": 900, "total_liability": 500}]}},
        {"status": "success", "data": {"type": "consolidated", "time_period": "yearly", "units_in": "crore",
            "cash_flow": [{"category": "operating", "history": [{"period": "Mar 2025", "value": 30}, {"period": "Mar 2024", "value": 25}]}]}},
    )


def test_parses_only_period_aligned_consolidated_metrics():
    result = metrics_from_responses(*_responses())
    assert result["FinancialPeriodEnd"] == "2025-03-31"
    assert result["RevenueGrowthPct"] == pytest.approx(20.0)
    assert result["ProfitGrowthPct"] == pytest.approx(20.0)
    assert result["OperatingCashFlowINR"] == 300_000_000
    assert result["MetricCalculationBasis"] == "ANNUAL_ALIGNED_STATEMENTS"


def test_rejects_inconsistent_balance_sheet_period():
    with pytest.raises(ValueError, match="common annual period"):
        metrics_from_responses(*_responses("Mar 2024"))


def test_missing_token_skips_without_request():
    class NoNetwork:
        def get(self, *args, **kwargs):
            raise AssertionError("network should not be called without token")

    result = fetch_upstox_fundamentals("INE002A01018", access_token="", session=NoNetwork())
    assert result["UpstoxStatus"] == "SKIPPED_NO_ACCESS_TOKEN"


def test_missing_isin_skips_without_request():
    class NoNetwork:
        def get(self, *args, **kwargs):
            raise AssertionError("network should not be called without ISIN")

    result = fetch_upstox_fundamentals("", access_token="test-token", session=NoNetwork())
    assert result["UpstoxStatus"] == "SKIPPED_NO_ISIN"


def test_provider_fallback_fills_only_missing_same_period_metrics(monkeypatch):
    result = metrics_from_responses(*_responses())
    monkeypatch.setattr("upstox_fundamentals.fetch_upstox_fundamentals", lambda _isin: result)
    fetched = {"RevenueGrowthPct": 10.0, "FinancialPeriodEnd": "2025-03-31",
               "MetricCalculationBasis": "ANNUAL_ALIGNED_STATEMENTS",
               "ProviderMetricSourcesJSON": '{"RevenueGrowthPct":"Yahoo Finance via yfinance"}'}
    diagnostic = {}
    _apply_upstox_fallback(fetched, diagnostic, "AAA", "INE000A01000")
    assert fetched["RevenueGrowthPct"] == 10.0
    assert fetched["ProfitGrowthPct"] == 20.0
    assert fetched["OperatingCashFlowINR"] == 300_000_000
    assert fetched["UpstoxStatus"] == "DATA_FOUND_PARTIAL_METRICS_ADDED"
    assert 'Upstox Fundamentals API' in fetched["ProviderMetricSourcesJSON"]


def test_provider_fallback_rejects_mismatched_period(monkeypatch):
    result = metrics_from_responses(*_responses())
    monkeypatch.setattr("upstox_fundamentals.fetch_upstox_fundamentals", lambda _isin: result)
    fetched = {"FinancialPeriodEnd": "2024-03-31", "MetricCalculationBasis": "ANNUAL_ALIGNED_STATEMENTS"}
    diagnostic = {}
    _apply_upstox_fallback(fetched, diagnostic, "AAA", "INE000A01000")
    assert "ProfitGrowthPct" not in fetched
    assert fetched["UpstoxStatus"] == "UPSTOX_PERIOD_MISMATCH"
