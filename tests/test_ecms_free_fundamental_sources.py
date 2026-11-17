import sys
from types import SimpleNamespace

import pandas as pd

import free_fundamental_sources as shared_free_sources

from strategies.ecms.free_fundamental_sources import (
    _select_exact_moneycontrol_hit,
    _strict_moneycontrol_factory,
)


def test_moneycontrol_selects_matching_result_id_not_library_first_result():
    hits = [
        {"sc_id": "WRONG_FIRST", "stock_name": "Other Industries Limited"},
        {"sc_id": "RIGHT_TARGET", "stock_name": "ABC Industries Ltd."},
    ]
    selected = _select_exact_moneycontrol_hit("ABC", "ABC Industries Limited", hits)
    assert selected == hits[1]
    assert selected["sc_id"] != "WRONG_FIRST"


def test_moneycontrol_identity_match_rejects_substring_only_company_name():
    hits = [{"sc_id": "MC123", "stock_name": "Reliance"}]
    assert _select_exact_moneycontrol_hit(
        "RELIANCE", "Reliance Industries Limited", hits
    ) is None


def test_moneycontrol_identity_match_rejects_ambiguous_duplicate_hits():
    hits = [
        {"sc_id": "MC123", "stock_name": "ABC Limited"},
        {"sc_id": "MC456", "stock_name": "ABC Ltd."},
    ]
    assert _select_exact_moneycontrol_hit("ABC", "ABC Limited", hits) is None


def test_ecms_moneycontrol_factory_returns_selected_hit_and_its_own_id(monkeypatch):
    wrong = {"sc_id": "WRONG_FIRST", "stock_name": "Other Industries Limited"}
    right = {"sc_id": "RIGHT_TARGET", "stock_name": "ABC Industries Ltd."}

    class FakeMoneyControl:
        def __init__(self):
            self.session = object()

        def get_ticker(self, search_text):
            return "WRONG_FIRST", [wrong, right]

    monkeypatch.setitem(
        sys.modules, "Fundamentals",
        SimpleNamespace(MoneyControl=FakeMoneyControl),
    )
    client = _strict_moneycontrol_factory("ABC", "ABC Industries Limited")()
    ticker_id, raw_hit = client.get_ticker("ABC Industries Limited")

    assert ticker_id == "RIGHT_TARGET"
    assert raw_hit == right


def test_ecms_moneycontrol_factory_fails_closed_when_no_exact_hit(monkeypatch):
    hits = [{"sc_id": "WRONG_FIRST", "stock_name": "ABC Holdings Limited"}]

    class FakeMoneyControl:
        def __init__(self):
            self.session = object()

        def get_ticker(self, search_text):
            return "WRONG_FIRST", hits

    monkeypatch.setitem(
        sys.modules, "Fundamentals",
        SimpleNamespace(MoneyControl=FakeMoneyControl),
    )
    client = _strict_moneycontrol_factory("ABC", "ABC Industries Limited")()
    ticker_id, raw_hits = client.get_ticker("ABC Industries Limited")

    assert ticker_id == ""
    assert raw_hits == hits



def test_ecms_metric_provenance_records_actual_moneycontrol_request_url(monkeypatch):
    class FakeMoneyControl:
        def __init__(self):
            self.session = None
            self._free_source_last_http = {}

        def _frame(self, reference_id, frame):
            self._free_source_last_http = {
                "url": (
                    "https://www.moneycontrol.com/mc/widget/mcfinancials/"
                    f"getFinancialData?referenceId={reference_id}&scId=MC123"
                )
            }
            return frame

        def get_ticker(self, search_text):
            return "MC123", {"ticker": "ABC", "sc_id": "MC123", "stock_name": "ABC Limited"}

        def get_ratios_mini_statement(self, ticker, statement_type="consolidated"):
            return self._frame("ratios", pd.DataFrame({"Mar 2026": [12.5]}, index=["EPS"]))

        def get_overview_mini_statement(self, ticker, statement_type="consolidated", statement_frequency=12):
            return self._frame("overview", pd.DataFrame())

        def get_income_mini_statement(self, ticker, statement_type="consolidated", statement_frequency=3):
            return self._frame("income", pd.DataFrame())

        def get_balance_sheet_mini_statement(self, ticker, statement_type="consolidated"):
            return self._frame("balance-sheet", pd.DataFrame())

        def get_cash_flow_mini_statement(self, ticker, statement_type="consolidated"):
            return self._frame("cash-flow", pd.DataFrame())

    fake_client = FakeMoneyControl()
    monkeypatch.setattr(
        shared_free_sources, "_instantiate_bounded_client", lambda factory: fake_client
    )
    result = shared_free_sources.fetch_free_fundamental_sources(
        "ABC",
        company_name="ABC Limited",
        missing_metrics={"EPS"},
        pause_seconds=0,
        source_factories={"moneycontrol": lambda: fake_client},
        capture_metric_source_urls=True,
    )

    assert result["metrics"]["EPS"] == 12.5
    assert result["metric_periods"]["EPS"] == "Mar 2026"
    assert result["metric_urls"]["EPS"].startswith(
        "https://www.moneycontrol.com/mc/widget/mcfinancials/getFinancialData?"
    )
    assert "referenceId=ratios" in result["metric_urls"]["EPS"]
    assert "scId=MC123" in result["metric_urls"]["EPS"]
    assert result["metric_urls"]["EPS"] != "https://www.moneycontrol.com/"


def test_operating_cash_flow_metric_is_requested_and_extracted_from_cash_flow_table(monkeypatch):
    class FakeMoneyControl:
        def __init__(self):
            self.session = None
            self._free_source_last_http = {}

        def _frame(self, reference_id, frame):
            self._free_source_last_http = {
                "url": (
                    "https://www.moneycontrol.com/mc/widget/mcfinancials/"
                    f"getFinancialData?referenceId={reference_id}&scId=MC123"
                )
            }
            return frame

        def get_ticker(self, search_text):
            return "MC123", {"ticker": "ABC", "sc_id": "MC123", "stock_name": "ABC Limited"}

        def get_ratios_mini_statement(self, ticker, statement_type="consolidated"):
            return self._frame("ratios", pd.DataFrame())

        def get_overview_mini_statement(self, ticker, statement_type="consolidated", statement_frequency=12):
            return self._frame("overview", pd.DataFrame())

        def get_income_mini_statement(self, ticker, statement_type="consolidated", statement_frequency=3):
            return self._frame("income", pd.DataFrame())

        def get_balance_sheet_mini_statement(self, ticker, statement_type="consolidated"):
            return self._frame("balance-sheet", pd.DataFrame())

        def get_cash_flow_mini_statement(self, ticker, statement_type="consolidated"):
            return self._frame(
                "cash-flow",
                pd.DataFrame({"Mar 2026": [125.0]}, index=["Cash from operating activities"]),
            )

    fake_client = FakeMoneyControl()
    monkeypatch.setattr(
        shared_free_sources, "_instantiate_bounded_client", lambda factory: fake_client
    )
    result = shared_free_sources.fetch_free_fundamental_sources(
        "ABC",
        company_name="ABC Limited",
        missing_metrics={"OperatingCashFlowINR"},
        pause_seconds=0,
        source_factories={"moneycontrol": lambda: fake_client},
        capture_metric_source_urls=True,
    )

    assert result["metrics"]["OperatingCashFlowINR"] == 125.0
    assert result["metric_periods"]["OperatingCashFlowINR"] == "Mar 2026"
    assert "referenceId=cash-flow" in result["metric_urls"]["OperatingCashFlowINR"]
