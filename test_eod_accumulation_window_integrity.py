import pandas as pd

from v8_layers_14_41 import _accumulation_score


def _history(rows=20):
    dates = pd.bdate_range(end="2026-10-23", periods=rows)
    return pd.DataFrame({
        "Date": dates,
        "HghPric": [105.0] * rows,
        "LwPric": [95.0] * rows,
        "ClsPric": [102.0] * rows,
        "TtlTradgVol": [1000.0] * rows,
    })


def test_accumulation_distribution_requires_exact_twenty_valid_sessions():
    assert pd.notna(_accumulation_score(_history(rows=20)))
    assert pd.isna(_accumulation_score(_history(rows=19)))


def test_accumulation_distribution_waits_when_any_session_has_missing_ohlcv():
    history = _history()
    history.loc[history.index[7], "HghPric"] = float("nan")
    assert pd.isna(_accumulation_score(history))


def test_accumulation_distribution_waits_on_duplicate_session_dates():
    history = _history()
    history.loc[history.index[-1], "Date"] = history.loc[history.index[-2], "Date"]
    assert pd.isna(_accumulation_score(history))


def test_accumulation_distribution_waits_on_invalid_flat_candle_or_negative_volume():
    history = _history()
    history.loc[history.index[-1], "HghPric"] = 95.0
    history.loc[history.index[-1], "LwPric"] = 95.0
    assert pd.isna(_accumulation_score(history))
    history = _history()
    history.loc[history.index[-1], "TtlTradgVol"] = -1
    assert pd.isna(_accumulation_score(history))
