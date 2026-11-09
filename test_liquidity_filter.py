from __future__ import annotations

import pandas as pd

from liquidity_filter import apply_liquidity_filter, MINIMUM_AVG_DAILY_TRADED_VALUE_INR


def history_for(value, symbol="ABC"):
    return [pd.DataFrame([{"TckrSymb": symbol, "TtlTrfVal": value}]) for _ in range(20)]


def test_relaxed_minimum_passes_low_medium_and_strong_tiers():
    candidates = pd.DataFrame({"TckrSymb": ["LOW", "MED", "STRONG", "REJECT"]})
    values = {"LOW": 15_000_000, "MED": 30_000_000,
              "STRONG": 50_000_000, "REJECT": 14_999_999}
    history = [
        pd.DataFrame([{"TckrSymb": symbol, "TtlTrfVal": value} for symbol, value in values.items()])
        for _ in range(20)
    ]
    qualified, audit = apply_liquidity_filter(candidates, history)
    assert MINIMUM_AVG_DAILY_TRADED_VALUE_INR == 15_000_000
    assert set(qualified["TckrSymb"]) == {"LOW", "MED", "STRONG"}
    tiers = audit.set_index("TckrSymb")["LiquidityTier"].to_dict()
    assert tiers == {"LOW": "LOW", "MED": "MEDIUM", "STRONG": "STRONG", "REJECT": "BELOW_MINIMUM"}


def test_missing_session_is_wait_for_data_not_pass():
    candidates = pd.DataFrame([{"TckrSymb": "ABC"}])
    qualified, audit = apply_liquidity_filter(candidates, history_for(60_000_000)[:19])
    assert qualified.empty
    assert audit.iloc[0]["LiquidityStatus"] == "WAIT_FOR_DATA"


def test_missing_traded_value_column_is_wait_for_data_not_pass():
    candidates = pd.DataFrame([{"TckrSymb": "ABC"}])
    history = [pd.DataFrame([{"TckrSymb": "ABC", "TtlTradgVol": 1000}]) for _ in range(20)]
    qualified, audit = apply_liquidity_filter(candidates, history)
    assert qualified.empty
    assert audit.iloc[0]["LiquidityStatus"] == "WAIT_FOR_DATA"



def test_duplicate_symbol_rows_in_a_session_are_wait_not_keep_last_pass():
    candidates = pd.DataFrame([{"TckrSymb": "ABC"}])
    history = history_for(60_000_000)
    history[7] = pd.DataFrame([
        {"TckrSymb": "ABC", "TtlTrfVal": 60_000_000},
        {"TckrSymb": "ABC", "TtlTrfVal": 1},
    ])
    qualified, audit = apply_liquidity_filter(candidates, history)
    assert qualified.empty
    assert audit.iloc[0]["LiquidityStatus"] == "WAIT_FOR_DATA"


def test_duplicate_explicit_session_dates_are_wait_not_twenty_sessions():
    candidates = pd.DataFrame([{"TckrSymb": "ABC"}])
    history = [
        pd.DataFrame([{"TckrSymb": "ABC", "TtlTrfVal": 60_000_000,
                       "Date": pd.Timestamp("2026-10-01") + pd.Timedelta(days=i)}])
        for i in range(20)
    ]
    history[19]["Date"] = history[18]["Date"]
    qualified, audit = apply_liquidity_filter(candidates, history)
    assert qualified.empty
    assert audit.iloc[0]["LiquidityStatus"] == "WAIT_FOR_DATA"
