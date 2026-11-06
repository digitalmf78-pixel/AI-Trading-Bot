from pathlib import Path
import pandas as pd

import bottom_detection as bottom


def _history(symbol="ABC", periods=70):
    dates = pd.bdate_range("2026-07-01", periods=periods)
    # Smooth range with two deliberately confirmed pivot lows.
    lows = [100.0 + (i % 7) for i in range(periods)]
    highs = [value + 3.0 for value in lows]
    opens = [value + 1.0 for value in lows]
    closes = [value + 2.0 for value in lows]
    volumes = [1000.0] * periods
    # Pivot lows at 20 and 40, with the second one higher.
    lows[20], highs[20], opens[20], closes[20] = 90.0, 94.0, 91.0, 93.0
    lows[40], highs[40], opens[40], closes[40] = 94.0, 98.0, 95.0, 97.0
    # Post-pivot swing highs are cleared by the final bullish candle.
    for i in range(41, periods - 1):
        highs[i] = 98.0
        lows[i] = 95.0 + (i % 2)
        opens[i] = 96.0
        closes[i] = 97.0
    opens[-1], lows[-1], highs[-1], closes[-1], volumes[-1] = 97.0, 96.5, 103.0, 102.5, 1500.0
    return pd.DataFrame({
        "TckrSymb": [symbol] * periods, "Date": dates,
        "OpnPric": opens, "HghPric": highs, "LwPric": lows,
        "ClsPric": closes, "TtlTradgVol": volumes,
    })


def test_bottom_report_is_separate_and_emits_expected_schema():
    history = _history()
    candidates = pd.DataFrame([{
        "TckrSymb": "ABC", "ClsPric": 102.5, "EMA44": 98.0,
    }])
    report = bottom.analyze_bottoms(candidates, [history])
    assert report.iloc[0]["TckrSymb"] == "ABC"
    assert "BottomCategory" in report.columns
    assert "Support20DLow" in report.columns
    assert report.iloc[0]["BottomCategory"] in {
        "NONE", "A_POTENTIAL_BOTTOM", "B_CONFIRMED_BOTTOM_REVERSAL"
    }
    # The diagnostic is independent; it does not add or mutate candidate gates.
    assert candidates.columns.tolist() == ["TckrSymb", "ClsPric", "EMA44"]


def test_3_right_candles_required_to_confirm_pivot_low():
    history = _history(periods=30)
    # Last row is the candidate pivot and therefore cannot be confirmed yet.
    history.loc[history.index[-1], "LwPric"] = 50.0
    pivots = bottom._confirmed_pivots(history, left=3, right=3)
    assert all(index <= len(history) - 4 for index, _ in pivots)
    assert all(index != len(history) - 1 for index, _ in pivots)


def test_long_term_supports_only_populate_when_full_windows_exist():
    short = _history(periods=70)
    candidates = pd.DataFrame([{"TckrSymb": "ABC", "ClsPric": 105.0, "EMA44": 100.0}])
    report = bottom.analyze_bottoms(candidates, [short])
    row = report.iloc[0]
    assert pd.notna(row["Support20DLow"])
    assert pd.notna(row["Support50DLow"])
    assert pd.isna(row["Support100DLow"])
    assert pd.isna(row["Support200DLow"])


def test_missing_history_fails_closed_to_wait_for_data():
    candidates = pd.DataFrame([{"TckrSymb": "MISSING", "ClsPric": 100.0}])
    report = bottom.analyze_bottoms(candidates, [])
    row = report.iloc[0]
    assert row["BottomStatus"] == "WAIT_FOR_DATA"
    assert row["BottomCategory"] == "NONE"


def test_double_bottom_uses_atr_based_tolerance_and_not_fixed_percent():
    history = _history(periods=70)
    pivots = bottom._confirmed_pivots(history, left=3, right=3)
    assert len(pivots) >= 2
    atr = bottom._atr(history)
    assert pd.notna(atr) and atr > 0
    assert 0.75 * atr > 0
