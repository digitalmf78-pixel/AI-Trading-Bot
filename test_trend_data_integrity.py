import pandas as pd

from volume_gainer import calculate_trend


def _history(rows=60):
    dates = pd.bdate_range(end="2026-10-23", periods=rows)
    return pd.DataFrame({
        "TckrSymb": ["AAA"] * rows,
        "Date": dates,
        "OpnPric": [99.0] * rows,
        "HghPric": [105.0] * rows,
        "LwPric": [95.0] * rows,
        "ClsPric": [100.0 + i * 0.2 for i in range(rows)],
        "TtlTradgVol": [1000.0] * rows,
    })


def _candidate():
    return pd.DataFrame([{
        "TckrSymb": "AAA", "RVOL": 1.4,
        "AvgVolume20D": 1000.0, "TtlTradgVol": 1400.0,
    }])


def test_complete_history_produces_ema44_trend_observation():
    result = calculate_trend(_candidate(), [_history()])
    row = result.iloc[0]
    assert row["TrendDataStatus"] == "COMPLETE"
    assert pd.notna(row["EMA20"])
    assert pd.notna(row["EMA44"])
    assert row["TrendClassification"] != "WAIT_FOR_DATA"


def test_missing_market_session_returns_wait_instead_of_backfilling_ema():
    full = _history(rows=60)
    missing_date = full.iloc[-5]["Date"]
    symbol_history = full[full["Date"] != missing_date].copy()
    market_calendar_row = full[full["Date"] == missing_date].copy()
    market_calendar_row["TckrSymb"] = "OTHER"
    combined = pd.concat([symbol_history, market_calendar_row], ignore_index=True)
    result = calculate_trend(_candidate(), [combined])
    row = result.iloc[0]
    assert row["TrendDataStatus"] == "WAIT_FOR_DATA"
    assert row["TrendClassification"] == "WAIT_FOR_DATA"
    assert pd.isna(row["EMA44"])


def test_missing_current_session_returns_wait():
    full = _history(rows=60)
    latest_date = full["Date"].max()
    symbol_history = full[full["Date"] != latest_date].copy()
    market_calendar_row = full[full["Date"] == latest_date].copy()
    market_calendar_row["TckrSymb"] = "OTHER"
    combined = pd.concat([symbol_history, market_calendar_row], ignore_index=True)
    result = calculate_trend(_candidate(), [combined])
    assert result.iloc[0]["TrendDataStatus"] == "WAIT_FOR_DATA"
    assert result.iloc[0]["TrendClassification"] == "WAIT_FOR_DATA"


def test_insufficient_history_returns_wait_not_partial_ema():
    result = calculate_trend(_candidate(), [_history(rows=49)])
    assert result.iloc[0]["TrendDataStatus"] == "WAIT_FOR_DATA"
    assert result.iloc[0]["TrendClassification"] == "WAIT_FOR_DATA"
