import pandas as pd

from v8_layers_14_41 import _accumulation_score, _validate_eod_window_frames


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


def _session_frames():
    prior_dates = pd.bdate_range(end="2026-11-06", periods=19)
    frames = [
        pd.DataFrame({"Date": [day], "TckrSymb": ["AAA"]})
        for day in prior_dates
    ]
    current = pd.DataFrame({"Date": [pd.Timestamp("2026-11-09")], "TckrSymb": ["AAA"]})
    return frames + [current]


def test_eod_window_accepts_nineteen_prior_sessions_plus_current_eod():
    complete, dates = _validate_eod_window_frames(_session_frames(), "2026-11-09")
    assert complete is True
    assert len(dates) == 20
    assert dates[-1] == pd.Timestamp("2026-11-09").date()


def test_eod_window_rejects_current_eod_missing_or_mislabeled():
    frames = _session_frames()
    frames[-1] = pd.DataFrame({"Date": [pd.Timestamp("2026-11-06")]})
    complete, dates = _validate_eod_window_frames(frames, "2026-11-09")
    assert complete is False and dates == []


def test_eod_window_rejects_prior_frame_on_or_after_eod():
    frames = _session_frames()
    frames[4] = pd.DataFrame({"Date": [pd.Timestamp("2026-11-09")]})
    complete, dates = _validate_eod_window_frames(frames, "2026-11-09")
    assert complete is False and dates == []


def test_eod_window_rejects_duplicate_or_out_of_order_sessions():
    frames = _session_frames()
    frames[5] = frames[4].copy()
    complete, dates = _validate_eod_window_frames(frames, "2026-11-09")
    assert complete is False and dates == []


def test_eod_window_rejects_incomplete_twenty_session_window():
    complete, dates = _validate_eod_window_frames(_session_frames()[:-1], "2026-11-09")
    assert complete is False and dates == []
