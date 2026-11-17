"""Two-sided ECMS U-Turn price-context observations (research only).

This complements the annual-EPS downside valuation-reset calculator. It does
not predict tops/bottoms or produce trading signals. All thresholds are
configurable research defaults and must not be treated as validated rules.
"""
from __future__ import annotations

import pandas as pd

CALCULATION_VERSION = "ecms-uturn-two-sided-v1"
DEFAULT_RSI_PERIOD = 14
DEFAULT_SMA_FAST = 20
DEFAULT_SMA_SLOW = 50
DEFAULT_OVERBOUGHT_RSI = 70.0
DEFAULT_OVERSOLD_RSI = 35.0
DEFAULT_EXTENSION_PCT = 10.0
DEFAULT_VOLUME_SPIKE_RATIO = 1.5


def _rsi_wilder(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.mask((avg_loss == 0) & (avg_gain > 0), 100.0)
    rsi = rsi.mask((avg_loss == 0) & (avg_gain == 0), 50.0)
    return rsi


def assess_two_sided_price_context(
    ohlcv: pd.DataFrame,
    *,
    downside_zone_low: float | None = None,
    downside_zone_high: float | None = None,
    rsi_period: int = DEFAULT_RSI_PERIOD,
    sma_fast: int = DEFAULT_SMA_FAST,
    sma_slow: int = DEFAULT_SMA_SLOW,
    overbought_rsi: float = DEFAULT_OVERBOUGHT_RSI,
    oversold_rsi: float = DEFAULT_OVERSOLD_RSI,
    extension_pct: float = DEFAULT_EXTENSION_PCT,
    volume_spike_ratio: float = DEFAULT_VOLUME_SPIKE_RATIO,
) -> dict:
    """Return a separate bottom/overextension observation from daily OHLCV.

    Input must contain completed, chronological NSE sessions with Date, High,
    Low, Close and Volume. The current session is treated as completed only
    because the caller supplies it; caller is responsible for session status.
    """
    if min(rsi_period, sma_fast, sma_slow) < 2 or sma_slow < sma_fast:
        raise ValueError("Periods must be >=2 and sma_slow >= sma_fast")
    if not 0 <= oversold_rsi < overbought_rsi <= 100:
        raise ValueError("RSI thresholds must satisfy 0 <= oversold < overbought <= 100")
    if extension_pct < 0 or volume_spike_ratio <= 0:
        raise ValueError("Extension must be non-negative and volume ratio positive")
    if (downside_zone_low is None) != (downside_zone_high is None):
        raise ValueError("Both downside zone bounds must be supplied together")
    if downside_zone_low is not None:
        if downside_zone_low <= 0 or downside_zone_high < downside_zone_low:
            raise ValueError("Invalid downside valuation-zone bounds")

    required = {"Date", "High", "Low", "Close", "Volume"}
    if not isinstance(ohlcv, pd.DataFrame) or not required.issubset(ohlcv.columns):
        return {"status": "WAIT_FOR_DATA", "reason": "OHLCV requires Date, High, Low, Close and Volume"}
    frame = ohlcv.copy()
    frame["_date"] = pd.to_datetime(frame["Date"], errors="coerce").dt.date
    if frame["_date"].isna().any():
        return {"status": "WAIT_FOR_DATA", "reason": "Missing or invalid session date"}
    if frame["_date"].duplicated().any():
        return {"status": "WAIT_FOR_DATA", "reason": "Duplicate session date"}
    frame = frame.sort_values("_date")
    if list(frame["_date"]) != sorted(frame["_date"]):
        return {"status": "WAIT_FOR_DATA", "reason": "Sessions are not chronological"}
    for col in ("High", "Low", "Close", "Volume"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    if frame[["High", "Low", "Close", "Volume"]].isna().any().any():
        return {"status": "WAIT_FOR_DATA", "reason": "OHLCV contains missing or non-numeric values"}
    if (frame[["High", "Low", "Close"]] <= 0).any().any() or (frame["Volume"] < 0).any():
        return {"status": "WAIT_FOR_DATA", "reason": "OHLC prices must be positive and volume non-negative"}
    if (frame["High"] < frame[["Low", "Close"]].max(axis=1)).any():
        return {"status": "WAIT_FOR_DATA", "reason": "High is below Low or Close"}
    if (frame["Low"] > frame[["High", "Close"]].min(axis=1)).any():
        return {"status": "WAIT_FOR_DATA", "reason": "Low is above High or Close"}
    if len(frame) < sma_slow + 1:
        return {"status": "WAIT_FOR_DATA", "reason": f"Need at least {sma_slow + 1} completed sessions"}

    close = frame["Close"]
    frame["_rsi"] = _rsi_wilder(close, rsi_period)
    frame["_sma_fast"] = close.rolling(sma_fast, min_periods=sma_fast).mean()
    frame["_sma_slow"] = close.rolling(sma_slow, min_periods=sma_slow).mean()
    frame["_prior_volume_avg"] = frame["Volume"].shift(1).rolling(20, min_periods=20).mean()
    last = frame.iloc[-1]
    previous = frame.iloc[-2]
    if pd.isna(last["_rsi"]) or pd.isna(previous["_rsi"]) or pd.isna(last["_sma_fast"]) or pd.isna(last["_sma_slow"]) or pd.isna(last["_prior_volume_avg"]) or last["_prior_volume_avg"] <= 0:
        return {"status": "WAIT_FOR_DATA", "reason": "Insufficient valid history for RSI, moving averages or prior-20-session volume"}

    latest_close = float(last["Close"])
    rsi = float(last["_rsi"])
    sma_fast_value = float(last["_sma_fast"])
    sma_slow_value = float(last["_sma_slow"])
    extension = (latest_close / sma_fast_value - 1) * 100
    volume_ratio = float(last["Volume"] / last["_prior_volume_avg"])
    in_downside_zone = (
        downside_zone_low is not None
        and downside_zone_low <= latest_close <= downside_zone_high
    )

    # A bottom-side watch requires valuation-zone proximity plus early price
    # and RSI stabilization; zone proximity alone is never confirmation.
    if in_downside_zone and rsi <= oversold_rsi and latest_close > float(previous["Close"]) and rsi > float(previous["_rsi"]):
        status = "BOTTOM_WATCH"
        reason = "Close is inside the supplied valuation-reset zone and price/RSI show one-session stabilization; not a confirmed bottom"
    elif in_downside_zone:
        status = "RESET_ZONE_ONLY"
        reason = "Close is inside the valuation-reset zone but bottom-side stabilization conditions are not all present"
    elif rsi >= overbought_rsi and extension >= extension_pct:
        status = "OVEREXTENDED"
        reason = "RSI and distance above the fast moving average both exceed configured research thresholds"
    elif rsi >= overbought_rsi or extension >= extension_pct:
        status = "STRETCHED"
        reason = "At least one configured overextension observation is present; confluence is incomplete"
    elif latest_close > sma_fast_value > sma_slow_value and rsi >= 55:
        status = "MOMENTUM_STRONG"
        reason = "Price and moving-average structure show positive momentum; this is not an overextension call"
    elif latest_close < sma_fast_value and rsi < 50 and volume_ratio >= volume_spike_ratio:
        status = "WEAKENING"
        reason = "Close is below the fast moving average with weak RSI and elevated volume versus prior 20 sessions"
    else:
        status = "NEUTRAL"
        reason = "No configured bottom-zone or overextension confluence is present"

    return {
        "status": status,
        "reason": reason,
        "session_date": last["_date"].isoformat(),
        "close": latest_close,
        "rsi": rsi,
        "previous_rsi": float(previous["_rsi"]),
        "sma_fast": sma_fast_value,
        "sma_slow": sma_slow_value,
        "extension_pct_vs_sma_fast": extension,
        "volume_ratio_vs_prior_20": volume_ratio,
        "inside_downside_valuation_zone": bool(in_downside_zone),
        "calculation_version": CALCULATION_VERSION,
        "interpretation": "Research observation only; not a buy/sell signal, confirmed top/bottom, or guaranteed support/resistance.",
    }
