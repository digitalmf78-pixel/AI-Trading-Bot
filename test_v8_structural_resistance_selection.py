"""Focused tests for V8 structural-resistance target selection.

Run: python test_v8_structural_resistance_selection.py
"""
import math
import pandas as pd
import v8_layers_14_41 as layers


def test_uses_nearest_observed_resistance_above_entry():
    row = pd.Series({
        "SRResistance": 29.70,
        "SRSwingHigh": 30.40,
        "RecentSwingHigh": 30.40,
        "SR20DHigh": 32.10,
        "SR50DHigh": 33.99,
        "High50D": 33.99,
    })
    level, source = layers._structural_resistance_candidate(row, 29.8485)
    assert level == 30.40, (level, source)
    assert source == "SR_SWING_HIGH", (level, source)


def test_prefers_nearest_overhead_level_not_highest_level():
    row = pd.Series({
        "SRResistance": 24.70,
        "SRSwingHigh": 26.90,
        "RecentSwingHigh": 25.80,
        "SR20DHigh": 26.20,
        "SR50DHigh": 26.90,
    })
    level, source = layers._structural_resistance_candidate(row, 24.8235)
    assert level == 25.80, (level, source)
    assert source == "RECENT_SWING_HIGH", (level, source)


def test_no_overhead_structure_stays_wait_for_data():
    row = pd.Series({
        "SRResistance": 118.90,
        "SRSwingHigh": 118.90,
        "RecentSwingHigh": 118.90,
        "SR20DHigh": 118.90,
        "SR50DHigh": 118.90,
        "High50D": 118.90,
    })
    level, source = layers._structural_resistance_candidate(row, 120.089)
    assert math.isnan(level), (level, source)
    assert source == "WAIT_FOR_DATA", source
    rr = layers._calculate_structural_risk_reward(120.089, 118.0, level, source)
    assert rr["RiskRewardStatus"] == "WAIT_FOR_DATA", rr
    assert math.isnan(rr["TargetPricePlan"]), rr


def test_observed_target_rr_pass_or_fail_is_calculated_from_structure():
    passing = layers._calculate_structural_risk_reward(100.0, 95.0, 110.0, "SR_50D_HIGH")
    assert passing["RiskReward"] == 2.0, passing
    assert passing["RiskRewardStatus"] == "PASS", passing
    assert passing["TargetSource"] == "SR_50D_HIGH", passing
    assert passing["StructuralResistanceUsed"] == 110.0, passing

    failing = layers._calculate_structural_risk_reward(100.0, 95.0, 108.0, "RECENT_SWING_HIGH")
    assert failing["RiskReward"] == 1.6, failing
    assert failing["RiskRewardStatus"] == "FAIL", failing
    assert failing["TargetPricePlan"] == 108.0, failing


def test_invalid_entry_or_stop_does_not_pass():
    result = layers._calculate_structural_risk_reward(100.0, 100.0, 120.0, "SR_50D_HIGH")
    assert result["RiskRewardStatus"] == "WAIT_FOR_DATA", result
    assert math.isnan(result["TargetPricePlan"]), result


def run():
    tests = [
        test_uses_nearest_observed_resistance_above_entry,
        test_prefers_nearest_overhead_level_not_highest_level,
        test_no_overhead_structure_stays_wait_for_data,
        test_observed_target_rr_pass_or_fail_is_calculated_from_structure,
        test_invalid_entry_or_stop_does_not_pass,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")
    print(f"ALL {len(tests)} STRUCTURAL RESISTANCE TESTS PASSED")


if __name__ == "__main__":
    run()
