import pandas as pd

from volume_gainer import calculate_breakout_pullback


def _history(rows=51, prior_volume=1000, current_volume=1000,
             current_close=100, current_open=99, current_high=102,
             current_low=98, prior_high=105, prior_low=95):
    dates = pd.bdate_range(end="2026-10-23", periods=rows)
    frame = pd.DataFrame({
        "TckrSymb": ["AAA"] * rows,
        "Date": dates,
        "OpnPric": [99.0] * rows,
        "HghPric": [float(prior_high)] * rows,
        "LwPric": [float(prior_low)] * rows,
        "ClsPric": [100.0] * rows,
        "TtlTradgVol": [float(prior_volume)] * rows,
    })
    frame.loc[frame.index[-1], ["OpnPric", "HghPric", "LwPric", "ClsPric", "TtlTradgVol"]] = [
        current_open, current_high, current_low, current_close, current_volume
    ]
    return frame


def _candidate(**overrides):
    row = {
        "TckrSymb": "AAA",
        "EMA20": 100.0,
        "EMA44": 100.0,
        "TrendClassification": "Bullish (Close > EMA44)",
        "LowVolumeDays5D": 0,
    }
    row.update(overrides)
    return pd.DataFrame([row])


def test_insufficient_prior_sessions_return_wait_not_partial_20d_or_50d_breakout():
    result = calculate_breakout_pullback(_candidate(), [_history(rows=20)])
    row = result.iloc[0]
    assert row["High20DDataStatus"] == "WAIT_FOR_DATA"
    assert row["High50DDataStatus"] == "WAIT_FOR_DATA"
    assert row["VolumeBaseline20DStatus"] == "WAIT_FOR_DATA"
    assert row["BreakoutStatus"] == "WAIT_FOR_DATA"
    assert row["PullbackStatus"] == "WAIT_FOR_DATA"
    assert row["SetupType"] == "WAIT_FOR_DATA"


def test_20d_window_can_be_complete_while_50d_window_remains_wait():
    result = calculate_breakout_pullback(_candidate(), [_history(rows=21)])
    row = result.iloc[0]
    assert row["High20DDataStatus"] == "COMPLETE"
    assert row["High50DDataStatus"] == "WAIT_FOR_DATA"
    assert row["VolumeBaseline20DStatus"] == "COMPLETE"
    assert row["BreakoutDataStatus"] == "PARTIAL_DATA"
    assert row["BreakoutStatus"] == "No Breakout"


def test_zero_volume_baseline_does_not_become_rvol_zero_or_no_breakout():
    result = calculate_breakout_pullback(
        _candidate(), [_history(rows=51, prior_volume=0, current_volume=1000)]
    )
    row = result.iloc[0]
    assert row["VolumeBaseline20DStatus"] == "WAIT_FOR_DATA"
    assert pd.isna(row["SetupRVOL"])
    assert row["BreakoutStatus"] == "WAIT_FOR_DATA"
    assert row["PullbackStatus"] == "WAIT_FOR_DATA"


def test_flat_candle_does_not_receive_synthetic_clv_or_false_no_breakout():
    result = calculate_breakout_pullback(
        _candidate(), [_history(
            rows=51, current_close=100, current_open=100,
            current_high=100, current_low=100, current_volume=2500,
        )]
    )
    row = result.iloc[0]
    assert row["BreakoutStatus"] == "WAIT_FOR_DATA"
    assert row["BreakoutDataStatus"] == "WAIT_FOR_DATA"
    assert row["PullbackStatus"] == "WAIT_FOR_DATA"


def test_existing_strong_breakout_thresholds_are_preserved():
    result = calculate_breakout_pullback(
        _candidate(), [_history(
            rows=51, current_close=111.5, current_open=109,
            current_high=112, current_low=108, current_volume=2500,
        )]
    )
    row = result.iloc[0]
    assert row["BreakoutStatus"] == "Strong Breakout"
    assert row["SetupType"] == "Breakout"
    assert row["SetupRVOL"] == 2.5


def test_existing_strong_pullback_thresholds_are_preserved():
    result = calculate_breakout_pullback(
        _candidate(LowVolumeDays5D=3), [_history(
            rows=51, current_close=101, current_open=100,
            current_high=102, current_low=98, current_volume=1000,
            prior_high=110, prior_low=90,
        )]
    )
    row = result.iloc[0]
    assert row["PullbackStatus"] == "Strong Pullback"
    assert row["SetupType"] == "Pullback"



def test_missing_market_session_is_not_replaced_by_an_older_symbol_row():
    full = _history(rows=51)
    missing_date = full.iloc[-5]["Date"]
    symbol_history = full[full["Date"] != missing_date].copy()
    market_calendar_row = full[full["Date"] == missing_date].copy()
    market_calendar_row["TckrSymb"] = "OTHER"
    combined = pd.concat([symbol_history, market_calendar_row], ignore_index=True)
    result = calculate_breakout_pullback(_candidate(), [combined])
    row = result.iloc[0]
    assert row["High20DDataStatus"] == "WAIT_FOR_DATA"
    assert row["VolumeBaseline20DStatus"] == "WAIT_FOR_DATA"
    assert row["BreakoutStatus"] == "WAIT_FOR_DATA"
    assert row["PullbackStatus"] == "WAIT_FOR_DATA"
