import pandas as pd

from free_fundamental_sources import fetch_free_fundamental_sources


class FakeMoneyControl:
    calls = []

    def get_ticker(self, symbol):
        self.calls.append(("moneycontrol", "lookup", symbol))
        return "MC123", [{"symbol": symbol}]

    def get_ratios_mini_statement(self, ticker, statement_type="consolidated"):
        self.calls.append(("moneycontrol", "ratios", ticker))
        return pd.DataFrame({"Latest": [18.5, 22.0, 0.5, 4.2, 35.0, 14.0]},
                            index=["Return on Equity", "ROCE", "Debt Equity", "Interest Coverage", "Gross Margin", "Net Profit Margin"])

    def get_overview_mini_statement(self, ticker, statement_type="consolidated", statement_frequency=12):
        self.calls.append(("moneycontrol", "overview", ticker))
        return pd.DataFrame({"Latest": [15.0]}, index=["Current Ratio"])

    def get_income_mini_statement(self, ticker, statement_type="consolidated", statement_frequency=3):
        self.calls.append(("moneycontrol", "income", ticker, statement_frequency))
        return pd.DataFrame({"Latest": [100.0]}, index=["Revenue"])

    def get_balance_sheet_mini_statement(self, ticker, statement_type="consolidated"):
        self.calls.append(("moneycontrol", "balance", ticker))
        return pd.DataFrame({"Latest": [200.0]}, index=["Total Assets"])

    def get_cash_flow_mini_statement(self, ticker, statement_type="consolidated"):
        self.calls.append(("moneycontrol", "cashflow", ticker))
        return pd.DataFrame({"Latest": [30.0]}, index=["Operating Cash Flow"])


class FakeTickertape:
    calls = []

    def get_ticker(self, symbol, search_place="stock"):
        self.calls.append(("tickertape", "lookup", symbol, search_place))
        return "TT123", [{"ticker": symbol, "sid": "TT123", "slug": "stocks/example-EXAM"}]

    def get_key_ratios(self, slug):
        self.calls.append(("tickertape", "ratios", slug))
        return pd.DataFrame({"value": [20.0]}, index=["ROCE"])

    def get_score_card(self, sid):
        self.calls.append(("tickertape", "scorecard", sid))
        return pd.DataFrame({"value": [19.0]}, index=["ROE"])

    def get_income_data(self, sid, time_horizon="interim", num_time_periods=12, view_type="normal"):
        self.calls.append(("tickertape", "income", sid, time_horizon, view_type))
        if view_type == "growth":
            return pd.DataFrame({"value": [12.0, 15.0]},
                                index=["Revenue Growth", "Net Profit Growth"])
        if view_type == "margin":
            return pd.DataFrame({"value": [35.0, 14.0]},
                                index=["Gross Margin", "Net Profit Margin"])
        return pd.DataFrame({"value": [100.0]}, index=["Revenue"])

    def get_balance_sheet_data(self, sid, num_time_periods=10):
        self.calls.append(("tickertape", "balance", sid))
        return pd.DataFrame({"value": [300.0]}, index=["Total Assets"])

    def get_cash_flow_data(self, sid, num_time_periods=10):
        self.calls.append(("tickertape", "cashflow", sid))
        return pd.DataFrame({"value": [50.0]}, index=["Operating Cash Flow"])

    def get_share_holding_pattern(self, slug):
        self.calls.append(("tickertape", "shareholding", slug))
        return pd.DataFrame({"category": ["Promoter", "FII"], "percentage": [52.0, 12.5]})

    def get_dividends_history(self, slug):
        self.calls.append(("tickertape", "dividends", slug))
        return pd.DataFrame({"year": [2025], "amount": [5.0]})

    def get_mutual_fund_holdings(self, slug):
        self.calls.append(("tickertape", "mutual_fund_holdings", slug))
        return pd.DataFrame({"fund": ["Fund A"]})

    def get_smallcase_holdings(self, slug):
        self.calls.append(("tickertape", "smallcase_holdings", slug))
        return pd.DataFrame({"smallcase": ["Basket A"]})


def test_fetches_all_free_sources_and_records_per_metric_provenance():
    FakeMoneyControl.calls = []
    FakeTickertape.calls = []
    result = fetch_free_fundamental_sources(
        "RELIANCE",
        missing_metrics={"ROEPercent", "ROCEPercent", "DebtToEquity", "InterestCoverage", "GrossMarginPct", "NetProfitMarginPct", "PromoterHoldingPct", "FIIHoldingPct"},
        pause_seconds=0,
        source_factories={
            "moneycontrol": FakeMoneyControl,
            "tickertape": FakeTickertape,
        },
    )
    assert result["metrics"]["ROEPercent"] == 18.5
    assert result["metrics"]["ROCEPercent"] == 22.0
    assert result["metrics"]["DebtToEquity"] == 0.5
    assert result["metrics"]["InterestCoverage"] == 4.2
    assert result["metrics"]["GrossMarginPct"] == 35.0
    assert result["metrics"]["NetProfitMarginPct"] == 14.0
    assert result["metrics"]["PromoterHoldingPct"] == 52.0
    assert result["metrics"]["FIIHoldingPct"] == 12.5
    assert result["metric_sources"]["ROEPercent"] == "Moneycontrol"
    assert result["providers"]["Moneycontrol"]["status"] == "DATA_FOUND"
    assert result["providers"]["Tickertape"]["status"] == "DATA_FOUND"
    assert any(call[0] == "tickertape" for call in FakeTickertape.calls)
    assert len([call for call in FakeMoneyControl.calls if call[1] != "lookup"]) == 6
    assert len([call for call in FakeTickertape.calls if call[1] != "lookup"]) == 13


def test_tickertape_fallback_fills_missing_ratio_when_moneycontrol_empty():
    class EmptyMoneyControl(FakeMoneyControl):
        def get_ratios_mini_statement(self, ticker, statement_type="consolidated"):
            return pd.DataFrame()

    result = fetch_free_fundamental_sources(
        "INFY",
        missing_metrics={"RevenueGrowthPct", "ProfitGrowthPct", "ROEPercent"},
        pause_seconds=0,
        source_factories={
            "moneycontrol": EmptyMoneyControl,
            "tickertape": FakeTickertape,
        },
    )
    assert result["metrics"]["RevenueGrowthPct"] == 12.0
    assert result["metrics"]["ProfitGrowthPct"] == 15.0
    assert result["metrics"]["ROEPercent"] == 19.0
    assert result["metric_sources"]["RevenueGrowthPct"] == "Tickertape"


def test_no_key_free_source_adapter_handles_unavailable_library():
    result = fetch_free_fundamental_sources(
        "TCS", missing_metrics={"ROEPercent"}, pause_seconds=0,
        source_factories={
            "moneycontrol": lambda: (_ for _ in ()).throw(ImportError("missing")),
            "tickertape": lambda: (_ for _ in ()).throw(ImportError("missing")),
        },
    )
    assert result["metrics"] == {}
    assert result["providers"]["Moneycontrol"]["status"] == "PROVIDER_ERROR"
    assert result["providers"]["Tickertape"]["status"] == "PROVIDER_ERROR"
