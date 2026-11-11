import json
from pathlib import Path

import pandas as pd
import pytest

from twelve_data_fundamentals import fetch_twelve_data_fundamentals


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    def get(self, url, params, timeout):
        endpoint = url.rsplit("/", 1)[-1]
        self.calls.append((endpoint, params, timeout))
        return FakeResponse(self.payloads[endpoint])


def _dates(count):
    return ["2026-09-30", "2026-06-30", "2026-03-31", "2025-12-31",
            "2025-09-30", "2025-06-30", "2025-03-31", "2024-12-31"][:count]


def _payloads(currency="INR", exchange="NSE"):
    income = []
    for index, day in enumerate(_dates(8)):
        scale = 1.0 if index < 4 else 0.8
        income.append({
            "fiscal_date": day,
            "sales": 1000 * scale,
            "net_income": 100 * scale,
            "operating_income": 200,
            "non_operating_interest": {"expense": 10},
        })
    balance = []
    for index, day in enumerate(_dates(5)):
        scale = 1.0 if index == 0 else 0.9
        balance.append({
            "fiscal_date": day,
            "assets": {"total_assets": 10000 * scale},
            "liabilities": {"current_liabilities": {"total_current_liabilities": 2000 * scale},
                            "total_debt": 1000 * scale},
            "shareholders_equity": {"total_shareholders_equity": 5000 * scale},
        })
    cash = [{
        "fiscal_date": day,
        "operating_activities": {"operating_cash_flow": 1000},
        "free_cash_flow": 700,
    } for day in _dates(4)]
    def wrap(key, rows):
        return {"meta": {"symbol": "TEST", "exchange": exchange, "mic_code": "XNSE", "currency": currency}, key: rows}
    return {
        "income_statement": wrap("income_statement", income),
        "balance_sheet": wrap("balance_sheet", balance),
        "cash_flow": wrap("cash_flow", cash),
    }


def test_twelve_data_calculates_aligned_quarterly_fundamentals_for_nse():
    session = FakeSession(_payloads())
    result = fetch_twelve_data_fundamentals("TEST", "test-key", session=session, asof_date="2026-10-01")
    assert result["exchange"] == "NSE"
    assert result["mic_code"] == "XNSE"
    assert result["calculation_basis"] == "QUARTERLY_TTM_ALIGNED_STATEMENTS"
    assert result["metrics"]["RevenueGrowthPct"] == pytest.approx(25.0)
    assert result["metrics"]["ProfitGrowthPct"] == pytest.approx(25.0)
    assert result["metrics"]["DebtToEquity"] == pytest.approx(0.2)
    assert result["metrics"]["InterestCoverage"] == pytest.approx(20.0)
    assert result["metrics"]["OperatingCashFlowINR"] == pytest.approx(4000.0)
    assert result["metrics"]["FreeCashFlowINR"] == pytest.approx(2800.0)
    assert len(session.calls) == 3
    assert all(call[1]["mic_code"] == "XNSE" for call in session.calls)


def test_twelve_data_rejects_non_nse_listing_even_if_symbol_matches():
    payloads = _payloads(exchange="BSE")
    session = FakeSession(payloads)
    with pytest.raises(ValueError, match="not confirmed as NSE"):
        fetch_twelve_data_fundamentals("TEST", "test-key", session=session)


def test_non_inr_currency_does_not_populate_absolute_inr_cashflow():
    session = FakeSession(_payloads(currency="USD"))
    result = fetch_twelve_data_fundamentals("TEST", "test-key", session=session)
    assert "RevenueGrowthPct" in result["metrics"]
    assert "DebtToEquity" in result["metrics"]
    assert "OperatingCashFlowINR" not in result["metrics"]
    assert "FreeCashFlowINR" not in result["metrics"]


def test_twelve_data_rejects_currency_mismatch_between_statements():
    payloads = _payloads(currency="INR")
    payloads["cash_flow"]["meta"]["currency"] = "USD"
    with pytest.raises(ValueError, match="statement currencies do not match"):
        fetch_twelve_data_fundamentals("TEST", "test-key", session=FakeSession(payloads))


def test_missing_api_key_fails_explicitly():
    with pytest.raises(ValueError, match="TWELVE_DATA_API_KEY"):
        fetch_twelve_data_fundamentals("TEST", "")


def test_provider_collection_merges_secondary_values_without_overwriting_existing(tmp_path, monkeypatch):
    import fundamental_data_provider as provider
    import twelve_data_fundamentals

    class EmptyTicker:
        info = {}
        financials = pd.DataFrame()
        balance_sheet = pd.DataFrame()
        cashflow = pd.DataFrame()
        quarterly_financials = pd.DataFrame()
        quarterly_balance_sheet = pd.DataFrame()
        quarterly_cashflow = pd.DataFrame()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "test-key")
    monkeypatch.setattr(
        twelve_data_fundamentals,
        "fetch_twelve_data_fundamentals",
        lambda symbol, api_key, asof_date=None: {
            "metrics": {"RevenueGrowthPct": 12.5, "ROEPercent": 15.0},
            "metric_periods": {"RevenueGrowthPct": "2026-09-30", "ROEPercent": "2026-09-30"},
            "metric_currencies": {"RevenueGrowthPct": "INR", "ROEPercent": "INR"},
            "metric_urls": {"RevenueGrowthPct": "https://api.twelvedata.com/income_statement", "ROEPercent": "https://api.twelvedata.com/balance_sheet"},
            "source": "Twelve Data",
            "source_url": "https://twelvedata.com/exchanges/XNSE?group=fundamentals",
            "currency": "INR", "exchange": "NSE", "mic_code": "XNSE",
            "financial_period_end": "2026-09-30",
        },
    )
    cache = Path("data/inputs/fundamental_metrics.csv")
    cache.parent.mkdir(parents=True)
    pd.DataFrame([{
        "TckrSymb": "TEST", "Source": "Manual verified filing",
        "SourceURL": "https://example.com/filing", "RevenueGrowthPct": 99.0,
    }]).to_csv(cache, index=False)
    result = provider.collect_missing_fundamentals(
        pd.DataFrame({"TckrSymb": ["TEST"]}), metrics_path=cache, enabled=True,
        ticker_factory=EmptyTicker, pause_seconds=0, asof_date="2026-10-01",
        filings_fetcher=lambda _cutoff: pd.DataFrame(),
    )
    row = result.set_index("TckrSymb").loc["TEST"]
    assert float(row["RevenueGrowthPct"]) == 99.0
    assert float(row["ROEPercent"]) == 15.0
    assert row["MetricCalculationBasis"] == "LEGACY_CACHE_BASIS_UNKNOWN"
    assert "Twelve Data" in row["MetricSourcesJSON"]
    assert "ROEPercent" in json.loads(row["MetricSourcesJSON"])
