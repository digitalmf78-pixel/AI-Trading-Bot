from __future__ import annotations

import pandas as pd

from liquidity_filter import apply_liquidity_filter


def history_for(values, symbol="ABC"):
    return [pd.DataFrame([{"TckrSymb": symbol, "TtlTrfVal": value}]) for value in values]


def test_average_daily_traded_value_exactly_two_crore_passes():
    candidates = pd.DataFrame([{"TckrSymb": "ABC", "DeliveryFilterStatus": "PASS_GE_60_PERCENT"}])
    qualified, audit = apply_liquidity_filter(candidates, history_for([20_000_000] * 20))
    assert len(qualified) == 1
    assert audit.iloc[0]["LiquidityStatus"] == "PASS_GE_2CR_AVG_DAILY_VALUE"
    assert audit.iloc[0]["AvgDailyTradedValue20D"] == 20_000_000


def test_average_daily_traded_value_below_two_crore_rejects():
    candidates = pd.DataFrame([{"TckrSymb": "ABC"}])
    qualified, audit = apply_liquidity_filter(candidates, history_for([19_999_999] * 20))
    assert qualified.empty
    assert audit.iloc[0]["LiquidityStatus"] == "FILTERED_OUT_LT_2CR_AVG_DAILY_VALUE"



def test_average_between_two_and_five_crore_now_passes():
    candidates = pd.DataFrame([{"TckrSymb": "ABC"}])
    qualified, audit = apply_liquidity_filter(candidates, history_for([30_000_000] * 20))
    assert len(qualified) == 1
    assert audit.iloc[0]["LiquidityStatus"] == "PASS_GE_2CR_AVG_DAILY_VALUE"
    assert audit.iloc[0]["AvgDailyTradedValue20D"] == 30_000_000

def test_missing_session_is_wait_for_data_not_pass():
    candidates = pd.DataFrame([{"TckrSymb": "ABC"}])
    qualified, audit = apply_liquidity_filter(candidates, history_for([60_000_000] * 19))
    assert qualified.empty
    assert audit.iloc[0]["LiquidityStatus"] == "WAIT_FOR_DATA"


def test_missing_traded_value_column_is_wait_for_data_not_pass():
    candidates = pd.DataFrame([{"TckrSymb": "ABC"}])
    history = [pd.DataFrame([{"TckrSymb": "ABC", "TtlTradgVol": 1000}]) for _ in range(20)]
    qualified, audit = apply_liquidity_filter(candidates, history)
    assert qualified.empty
    assert audit.iloc[0]["LiquidityStatus"] == "WAIT_FOR_DATA"


def test_pipeline_order_rvol_delivery_fundamentals_then_liquidity():
    from pathlib import Path
    source = Path("volume_gainer.py").read_text(encoding="utf-8")
    rvol = source.index("STEP 3: LOAD HISTORY AND CALCULATE RVOL BEFORE DELIVERY")
    delivery = source.index("STEP 4: TWO DELIVERY CATEGORIES, AFTER RVOL > 1.5")
    fundamental = source.index("STEP 5: FUNDAMENTAL DATA COLLECTION FOR ALL DELIVERY A/B STOCKS")
    liquidity = source.index("STEP 6: EXISTING LIQUIDITY FILTER")
    technical = source.index("STEP 7: PRICE + VOLUME")
    assert rvol < delivery < fundamental < liquidity < technical
    assert "AvgDailyTradedValue20D" in source
