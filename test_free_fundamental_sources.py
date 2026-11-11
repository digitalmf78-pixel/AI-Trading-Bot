import pandas as pd

from free_fundamental_sources import fetch_free_fundamental_sources, _configure_bounded_session, _instantiate_bounded_client, _extract_ratio, _extract_ratio_observation, _extract_annual_growth, _number, ALIASES


class FakeMoneyControl:
    calls = []

    def get_ticker(self, symbol):
        self.calls.append(("moneycontrol", "lookup", symbol))
        return "MC123", [{"symbol": symbol}]

    def get_ratios_mini_statement(self, ticker, statement_type="consolidated"):
        self.calls.append(("moneycontrol", "ratios", ticker))
        return pd.DataFrame({"Latest": [18.5, 22.0, 0.5, 4.2, 35.0, 14.0, 1.8, 1.2, 45.0, 20.0, 88.0, 640.0]},
                            index=["Return on Equity", "ROCE", "Debt Equity", "Interest Coverage", "Gross Margin", "Net Profit Margin", "Current Ratio", "Quick Ratio", "Return on Networth / Equity (%)", "Gross Profit Margin (%)", "Basic EPS (Rs.)", "Book Value [Excl. Reval Reserve]/Share (Rs.)"])

    def get_overview_mini_statement(self, ticker, statement_type="consolidated", statement_frequency=12):
        self.calls.append(("moneycontrol", "overview", ticker))
        return pd.DataFrame({"headings": ["Revenue", "Net Profit"], "2025": [100.0, 10.0], "2026": [120.0, 13.0]})

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

    _base_url = "https://api.tickertape.in"

    def hit_and_get_data(self, url, params=None):
        self.calls.append(("tickertape", "search", params["text"], params["types"]))
        return {"data": {"items": [{
            "ticker": str(params["text"]).upper(),
            "sid": "TT123",
            "slug": "stocks/example-EXAM",
        }]}}

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
        missing_metrics={"ROEPercent", "ROCEPercent", "DebtToEquity", "InterestCoverage", "GrossMarginPct", "NetProfitMarginPct", "CurrentRatio", "QuickRatio", "PromoterHoldingPct", "FIIHoldingPct", "RevenueGrowthPct", "ProfitGrowthPct"},
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
    assert result["metrics"]["CurrentRatio"] == 1.8
    assert result["metrics"]["QuickRatio"] == 1.2
    assert result["metrics"]["RevenueGrowthPct"] == 20.0
    assert result["metrics"]["ProfitGrowthPct"] == 30.0
    assert result["metric_periods"]["RevenueGrowthPct"] == "FY2025->FY2026"
    assert result["metrics"]["PromoterHoldingPct"] == 52.0
    assert result["metrics"]["FIIHoldingPct"] == 12.5
    assert result["metric_sources"]["ROEPercent"] == "Moneycontrol"
    assert result["metric_alternates"]["ROEPercent"][0]["source"] == "Tickertape"
    assert result["metric_alternates"]["ROEPercent"][0]["value"] == 19.0
    assert result["providers"]["Moneycontrol"]["status"] == "DATA_FOUND"
    assert result["providers"]["Tickertape"]["status"] == "DATA_FOUND"
    assert any(call[0] == "tickertape" for call in FakeTickertape.calls)
    assert len([call for call in FakeMoneyControl.calls if call[1] != "lookup"]) == 6
    assert len([call for call in FakeTickertape.calls if call[1] != "search"]) == 9


def test_tickertape_fallback_fills_missing_ratio_when_moneycontrol_empty():
    class EmptyMoneyControl(FakeMoneyControl):
        def get_ratios_mini_statement(self, ticker, statement_type="consolidated"):
            return pd.DataFrame()

        def get_overview_mini_statement(self, ticker, statement_type="consolidated", statement_frequency=12):
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


def test_wrong_company_search_result_is_rejected_before_fundamentals_fetch():
    class WrongMoneyControl:
        def get_ticker(self, search_text):
            return "MC999", {"symbol": "OTHER", "stock_name": "Other Company Ltd"}

        def get_ratios_mini_statement(self, *args, **kwargs):
            raise AssertionError("wrong-company data must never be fetched")

    class NoTickertape:
        _base_url = "https://api.tickertape.in"

        def hit_and_get_data(self, url, params=None):
            return {"data": {"items": []}}

    result = fetch_free_fundamental_sources(
        "RELIANCE", company_name="Reliance Industries Limited",
        missing_metrics={"ROEPercent"}, pause_seconds=0,
        source_factories={"moneycontrol": WrongMoneyControl, "tickertape": NoTickertape},
    )
    assert result["metrics"] == {}
    assert result["providers"]["Moneycontrol"]["status"] == "IDENTITY_UNVERIFIED"


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

def test_free_source_http_session_has_bounded_timeout_and_no_retries():
    class FakeSession:
        def __init__(self):
            self.mounts = {}
            self.last_kwargs = None

        def mount(self, prefix, adapter):
            self.mounts[prefix] = adapter

        def get(self, url, *args, **kwargs):
            self.last_kwargs = kwargs
            return "ok"

    class FakeClient:
        def __init__(self):
            self.session = FakeSession()

    client = FakeClient()
    _configure_bounded_session(client)
    assert client.session.mounts["https://"].max_retries.total == 0
    assert client.session.mounts["http://"].max_retries.total == 0
    assert client.session.get("https://example.invalid") == "ok"
    assert client.session.last_kwargs["timeout"] == (4, 8)

def test_constructor_requests_are_bounded_before_client_initialization(monkeypatch):
    from types import SimpleNamespace
    from requests import Session

    observed = {}

    def fake_get(session, url, *args, **kwargs):
        observed.update(kwargs)
        return object()

    monkeypatch.setattr(Session, "get", fake_get)

    def factory():
        session = Session()
        session.get("https://example.invalid")
        return SimpleNamespace(session=session)

    client = _instantiate_bounded_client(factory)
    assert observed["timeout"] == (4, 8)
    assert client.session.adapters["https://"].max_retries.total == 0

def test_moneycontrol_ratios_column_is_mapped_to_metric():
    frame = pd.DataFrame({
        "ratios": ["Return on Equity", "ROCE", "Debt Equity"],
        "Mar 2026": ["18.5%", "22.0%", "0.50"],
    })
    assert _extract_ratio(frame, ALIASES["ROEPercent"]) == 18.5
    assert _extract_ratio(frame, ALIASES["ROCEPercent"]) == 22.0
    assert _extract_ratio(frame, ALIASES["DebtToEquity"]) == 0.5

def test_moneycontrol_quarterly_and_annual_statement_heading_columns_are_mapped():
    quarterly = pd.DataFrame({
        "Quarterly": ["Total Revenue", "Net Profit"],
        "Sep 2026": ["125.0", "18.0"],
        "Jun 2026": ["110.0", "16.0"],
    })
    annual = pd.DataFrame({
        "Annual": ["Total Revenue", "Net Profit"],
        "Mar 2026": ["500.0", "70.0"],
    })
    assert _extract_ratio(quarterly, ("Total Revenue",)) == 125.0
    assert _extract_ratio(annual, ("Net Profit",)) == 70.0

def test_actual_moneycontrol_live_ratio_labels_map_exactly():
    frame = pd.DataFrame({
        "ratios": [
            "Gross Profit Margin (%)",
            "Operating Margin (%)",
            "Net Profit Margin (%)",
            "Return on Networth / Equity (%)",
            "ROCE (%)",
            "Current Ratio (X)",
            "Quick Ratio (X)",
            "Debt to Equity (x)",
            "Interest Coverage Ratios (X)",
            "Basic EPS (Rs.)",
            "Book Value [Excl. Reval Reserve]/Share (Rs.)",
            "Asset Turnover Ratio (%)",
        ],
        "Mar 2026": ["35.0%", "20.0%", "12.0%", "18.0%", "22.0%", "1.8x", "1.2x", "0.5x", "4.2x", "88.0", "640.0", "0.7"],
    })
    expectations = {
        "GrossMarginPct": 35.0,
        "OperatingMarginPct": 20.0,
        "NetProfitMarginPct": 12.0,
        "ROEPercent": 18.0,
        "ROCEPercent": 22.0,
        "CurrentRatio": 1.8,
        "QuickRatio": 1.2,
        "DebtToEquity": 0.5,
        "InterestCoverage": 4.2,
        "EPS": 88.0,
        "BookValuePerShare": 640.0,
        "AssetTurnover": 0.7,
    }
    for metric, expected in expectations.items():
        value, period = _extract_ratio_observation(frame, ALIASES[metric])
        assert value == expected, metric
        assert period == "Mar 2026", metric


def test_moneycontrol_annual_growth_requires_consecutive_years_and_positive_base():
    overview = pd.DataFrame({
        "headings": ["Revenue", "Net Profit"],
        "2024": [100.0, 10.0],
        "2025": [120.0, 12.0],
        "2026": [150.0, 15.0],
    })
    assert _extract_annual_growth(overview, ("revenue",)) == (25.0, "FY2025->FY2026")
    assert _extract_annual_growth(overview, ("net profit",)) == (25.0, "FY2025->FY2026")

    gap = pd.DataFrame({"headings": ["Revenue"], "2024": [100.0], "2026": [150.0]})
    assert _extract_annual_growth(gap, ("revenue",)) == (None, "")

    non_positive = pd.DataFrame({"headings": ["Revenue"], "2025": [0.0], "2026": [150.0]})
    assert _extract_annual_growth(non_positive, ("revenue",)) == (None, "")


def test_number_parser_handles_display_units_but_rejects_ranges():
    assert _number("₹1,234.5 Cr.") == 1234.5
    assert _number("(1,234.5)") == -1234.5
    assert _number("1.25x") == 1.25
    assert _number("10-12") is None
