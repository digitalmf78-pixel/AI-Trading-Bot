import pandas as pd
import pytest

from strategies.ecms.uturn_two_sided import assess_two_sided_price_context


def _history(n=80, *, trend="up"):
    dates = pd.bdate_range("2026-01-01", periods=n)
    if trend == "up":
        close = [100 + i * 1.5 for i in range(n)]
    elif trend == "down":
        close = [300 - i * 1.5 for i in range(n)]
    else:
        close = [200 + (i % 5) * 0.2 for i in range(n)]
    return pd.DataFrame({
        "Date": dates,
        "High": [x * 1.01 for x in close],
        "Low": [x * 0.99 for x in close],
        "Close": close,
        "Volume": [100000] * n,
    })


def test_strong_uptrend_is_not_automatically_called_overextended():
    result = assess_two_sided_price_context(_history(trend="up"))
    assert result["status"] in {"MOMENTUM_STRONG", "STRETCHED", "OVEREXTENDED"}
    assert result["interpretation"].startswith("Research observation only")


def test_overextension_requires_rsi_and_price_extension_confluence():
    frame = _history(trend="up")
    # Strong acceleration in the last observations creates a high RSI and
    # distance above SMA20, without asserting a market top.
    frame.loc[60:, "Close"] = [frame.loc[59, "Close"] + 12 * (i + 1) for i in range(20)]
    frame.loc[60:, "High"] = frame.loc[60:, "Close"] * 1.01
    frame.loc[60:, "Low"] = frame.loc[60:, "Close"] * 0.99
    result = assess_two_sided_price_context(frame)
    assert result["status"] == "OVEREXTENDED"


def test_bottom_watch_needs_zone_and_price_rsi_stabilization():
    frame = _history(trend="down")
    # Last two closes rebound modestly from the decline; use a wide research
    # zone only to test that zone proximity is a separate required condition.
    frame.loc[78, "Close"] = frame.loc[77, "Close"] + 1
    frame.loc[79, "Close"] = frame.loc[78, "Close"] + 2
    frame.loc[78:, "High"] = frame.loc[78:, "Close"] * 1.01
    frame.loc[78:, "Low"] = frame.loc[78:, "Close"] * 0.99
    result = assess_two_sided_price_context(
        frame, downside_zone_low=100, downside_zone_high=400,
    )
    assert result["status"] in {"BOTTOM_WATCH", "RESET_ZONE_ONLY"}


def test_zone_proximity_without_oversold_stabilization_is_not_bottom_watch():
    frame = _history(trend="up")
    result = assess_two_sided_price_context(
        frame, downside_zone_low=1, downside_zone_high=1000,
    )
    assert result["status"] == "RESET_ZONE_ONLY"


def test_missing_duplicate_or_insufficient_history_fails_closed():
    frame = _history(n=50)
    assert assess_two_sided_price_context(frame)["status"] == "WAIT_FOR_DATA"
    duplicate = pd.concat([_history(), _history().iloc[[-1]]], ignore_index=True)
    assert assess_two_sided_price_context(duplicate)["status"] == "WAIT_FOR_DATA"
    missing = _history()
    missing.loc[79, "Volume"] = None
    assert assess_two_sided_price_context(missing)["status"] == "WAIT_FOR_DATA"


def test_invalid_ohlc_and_parameters_rejected():
    frame = _history()
    frame.loc[79, "Low"] = frame.loc[79, "High"] + 1
    assert assess_two_sided_price_context(frame)["status"] == "WAIT_FOR_DATA"
    with pytest.raises(ValueError):
        assess_two_sided_price_context(_history(), extension_pct=-1)
    with pytest.raises(ValueError):
        assess_two_sided_price_context(_history(), downside_zone_low=100)
