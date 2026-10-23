from __future__ import annotations

import pandas as pd

from liquidity_filter import apply_liquidity_filter


def history_for(values, symbol="ABC"):
    return [pd.DataFrame([{"TckrSymb": symbol, "TtlTrfVal": value}]) for value in values]


def test_average_daily_traded_value_exactly_five_crore_passes():
    candidates = pd.DataFrame([{"TckrSymb": "ABC", "DeliveryFilterStatus": "PASS_GE_60_PERCENT"}])
    qualified, audit = apply_liquidity_filter(candidates, history_for([50_000_000] * 20))
    assert len(qualified) == 1
    assert audit.iloc[0]["LiquidityStatus"] == "PASS_GE_5CR_AVG_DAILY_VALUE"
    assert audit.iloc[0]["AvgDailyTradedValue20D"] == 50_000_000


def test_average_daily_traded_value_below_five_crore_rejects():
    candidates = pd.DataFrame([{"TckrSymb": "ABC"}])
    qualified, audit = apply_liquidity_filter(candidates, history_for([49_999_999] * 20))
    assert qualified.empty
    assert audit.iloc[0]["LiquidityStatus"] == "FILTERED_OUT_LT_5CR_AVG_DAILY_VALUE"


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


def test_pipeline_order_rvol_then_delivery_liquidity_fundamental():
    from pathlib import Path
    source = Path("volume_gainer.py").read_text(encoding="utf-8")
    rvol = source.index("STEP 3: LOAD HISTORY AND CALCULATE RVOL BEFORE DELIVERY")
    delivery = source.index("STEP 4: TWO DELIVERY CATEGORIES, AFTER RVOL > 1.5")
    liquidity = source.index("STEP 5: EXISTING LIQUIDITY FILTER")
    fundamental = source.index("STEP 6: EXISTING FUNDAMENTAL FILTER")
    technical = source.index("STEP 7: PRICE + VOLUME")
    assert rvol < delivery < liquidity < fundamental < technical
    assert "AvgDailyTradedValue20D" in source
