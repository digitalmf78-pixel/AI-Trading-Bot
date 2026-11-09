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
