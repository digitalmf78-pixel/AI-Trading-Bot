import sys
from types import SimpleNamespace

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
