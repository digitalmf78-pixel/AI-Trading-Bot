import pandas as pd

from volume_gainer import calculate_support_resistance


def _history(rows=21):
    dates = pd.bdate_range(end="2026-10-23", periods=rows)
    return pd.DataFrame({
        "TckrSymb": ["AAA"] * rows,
        "Date": dates,
        "OpnPric": [99.0] * rows,
        "HghPric": [105.0] * rows,
        "LwPric": [95.0] * rows,
        "ClsPric": [100.0] * rows,
        "TtlTradgVol": [1000.0] * rows,
    })


def _candidate():
    return pd.DataFrame([{"TckrSymb": "AAA", "EMA20": 100.0, "EMA44": 99.0}])


def test_exact_20d_and_50d_resistance_windows_have_independent_statuses():
    result = calculate_support_resistance(_candidate(), [_history(rows=21)])
    row = result.iloc[0]
    assert row["SR20DDataStatus"] == "COMPLETE"
    assert row["SR50DDataStatus"] == "WAIT_FOR_DATA"
    assert row["SR100DDataStatus"] == "WAIT_FOR_DATA"
    assert row["SR200DDataStatus"] == "WAIT_FOR_DATA"
    assert row["SRDataStatus"] == "PARTIAL_DATA"
    assert pd.notna(row["SR20DHigh"])


def test_200_session_history_completes_all_rolling_resistance_windows():
    result = calculate_support_resistance(_candidate(), [_history(rows=201)])
    row = result.iloc[0]
    assert row["SR20DDataStatus"] == "COMPLETE"
    assert row["SR50DDataStatus"] == "COMPLETE"
    assert row["SR100DDataStatus"] == "COMPLETE"
    assert row["SR200DDataStatus"] == "COMPLETE"
    assert row["SRDataStatus"] == "COMPLETE"


def test_missing_symbol_session_is_not_backfilled_from_older_data():
    full = _history(rows=51)
    missing_date = full.iloc[-5]["Date"]
    symbol_history = full[full["Date"] != missing_date].copy()
    market_calendar_row = full[full["Date"] == missing_date].copy()
    market_calendar_row["TckrSymb"] = "OTHER"
    combined = pd.concat([symbol_history, market_calendar_row], ignore_index=True)
    result = calculate_support_resistance(_candidate(), [combined])
    row = result.iloc[0]
    assert row["SR20DDataStatus"] == "WAIT_FOR_DATA"
    assert row["SR50DDataStatus"] == "WAIT_FOR_DATA"
    assert row["SRDataStatus"] == "PARTIAL_DATA"


def test_empty_candidate_frame_preserves_merge_key_and_status_columns():
    empty = pd.DataFrame(columns=["TckrSymb", "ClsPric"])
    result = calculate_support_resistance(empty, [])
    assert result.empty
    assert "TckrSymb" in result.columns
    assert "SRStatus" in result.columns
    assert "SRDataStatus" in result.columns



def test_invalid_current_ohlc_returns_wait_for_data():
    history = _history(rows=21)
    history.loc[history.index[-1], ["OpnPric", "HghPric", "LwPric", "ClsPric"]] = [
        110, 105, 100, 104
    ]
    row = calculate_support_resistance(_candidate(), [history]).iloc[0]
    assert row["SRStatus"] == "WAIT_FOR_DATA"
    assert row["SRDataStatus"] == "WAIT_FOR_DATA"


def test_invalid_high_low_order_in_rolling_window_is_not_accepted():
    history = _history(rows=21)
    history.loc[history.index[-5], ["HghPric", "LwPric"]] = [90, 95]
    row = calculate_support_resistance(_candidate(), [history]).iloc[0]
    assert row["SR20DDataStatus"] == "WAIT_FOR_DATA"
    assert pd.isna(row["SR20DHigh"])


def test_duplicate_candidate_symbols_do_not_multiply_sr_output_rows():
    candidates = pd.concat([_candidate(), _candidate()], ignore_index=True)
    row = calculate_support_resistance(candidates, [_history(rows=21)])
    assert len(row) == 2
    assert row["SRStatus"].eq("WAIT_FOR_DATA").all()


def test_duplicate_symbol_session_is_wait_for_data():
    history = _history(rows=21)
    history = pd.concat([history, history.iloc[[-5]]], ignore_index=True)
    row = calculate_support_resistance(_candidate(), [history]).iloc[0]
    assert row["SRDataStatus"] == "WAIT_FOR_DATA"
    assert row["SR20DDataStatus"] == "WAIT_FOR_DATA"
