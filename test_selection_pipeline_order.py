"""Guard the V8 selection order agreed with the user.

This is a structural regression test: Delivery is checked before RVOL Top 20,
then liquidity is applied to the Top 20 before technical analysis.
"""
from pathlib import Path


def test_delivery_rvol_liquidity_order():
    source = Path(__file__).with_name("volume_gainer.py").read_text(encoding="utf-8")
    delivery = source.index("STEP 2A: MANDATORY DELIVERY-FIRST GATE")
    rvol_top20 = source.index("result = select_top20_by_rvol(result, eod_date)")
    liquidity = source.index("STEP 6B: LIQUIDITY FILTER — AFTER RVOL TOP 20")
    technical = source.index("STEP 7: PRICE + VOLUME — only delivery-qualified, liquid Top 20")
    assert delivery < rvol_top20 < liquidity < technical


def test_liquidity_not_applied_before_rvol_top20():
    source = Path(__file__).with_name("volume_gainer.py").read_text(encoding="utf-8")
    early_region = source[source.index("STEP 2A: MANDATORY DELIVERY-FIRST GATE"):source.index("result = select_top20_by_rvol(result, eod_date)")]
    assert "apply_liquidity_filter(" not in early_region
