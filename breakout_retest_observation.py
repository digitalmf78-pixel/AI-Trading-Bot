"""Descriptive post-breakout retest observations.

This module reuses the existing V8 breakout definitions solely to locate a
historical breakout event. It does not introduce a retest time limit, price
buffer, confirmation gate, ranking change, or trade signal.
"""
from __future__ import annotations

import math
import pandas as pd


_REQUIRED = {"TckrSymb", "Date", "OpnPric", "HghPric", "LwPric", "ClsPric", "TtlTradgVol"}
_OUTPUT = [
    "TckrSymb", "RetestObservationStatus", "LastBreakoutDate",
    "BreakoutReferenceLevel", "SessionsSinceBreakout",
    "PostBreakoutLowestLow", "PostBreakoutHighestHigh", "PostBreakoutLastClose",
    "PostBreakoutLowestLowVsLevelPct", "PostBreakoutHighestHighVsLevelPct",
    "PostBreakoutClosesAboveLevelCount", "PostBreakoutClosesBelowLevelCount",
    "PostBreakoutClosesAtLevelCount", "PostBreakoutCloseVsLevelPct", "ExactLevelTouchObserved",
    "FirstExactLevelTouchDate", "BreakoutDayVolume",
    "PostBreakoutAverageVolume", "PostBreakoutVolumeVsBreakoutPct",
]


def _number(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else float("nan")
    except (TypeError, ValueError):
        return float("nan")


def _valid_candle(row):
    values = [_number(row.get(name)) for name in (
        "OpnPric", "HghPric", "LwPric", "ClsPric", "TtlTradgVol"
    )]
    opn, high, low, close, volume = values
    return (
        all(math.isfinite(x) and x > 0 for x in (opn, high, low, close))
        and math.isfinite(volume) and volume >= 0
        and high >= max(opn, close) and low <= min(opn, close)
        and high >= low
    )


def _wait(symbol):
    return {
        "TckrSymb": symbol,
        "RetestObservationStatus": "WAIT_FOR_DATA",
        "LastBreakoutDate": None,
        "BreakoutReferenceLevel": float("nan"),
        "SessionsSinceBreakout": float("nan"),
        "PostBreakoutLowestLow": float("nan"),
        "PostBreakoutHighestHigh": float("nan"),
        "PostBreakoutLastClose": float("nan"),
        "PostBreakoutLowestLowVsLevelPct": float("nan"),
        "PostBreakoutHighestHighVsLevelPct": float("nan"),
        "PostBreakoutClosesAboveLevelCount": float("nan"),
        "PostBreakoutClosesBelowLevelCount": float("nan"),
        "PostBreakoutClosesAtLevelCount": float("nan"),
        "PostBreakoutCloseVsLevelPct": float("nan"),
        "ExactLevelTouchObserved": "WAIT_FOR_DATA",
        "FirstExactLevelTouchDate": None,
        "BreakoutDayVolume": float("nan"),
        "PostBreakoutAverageVolume": float("nan"),
        "PostBreakoutVolumeVsBreakoutPct": float("nan"),
    }


def build_breakout_retest_observation(candidates, historical):
    """Return one descriptive observation row per input candidate row."""
    if candidates is None or candidates.empty or "TckrSymb" not in candidates.columns:
        return pd.DataFrame(columns=_OUTPUT)

    frames = [frame.copy() for frame in (historical or [])
              if frame is not None and not frame.empty]
    if not frames or any(not _REQUIRED.issubset(frame.columns) for frame in frames):
        return pd.DataFrame([_wait(s) for s in candidates["TckrSymb"]], columns=_OUTPUT)

    data = pd.concat(frames, ignore_index=True)
    data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
    data = data.dropna(subset=["Date"]).copy()
    if data.empty:
        return pd.DataFrame([_wait(s) for s in candidates["TckrSymb"]], columns=_OUTPUT)

    data["Date"] = data["Date"].dt.date
    for col in ("OpnPric", "HghPric", "LwPric", "ClsPric", "TtlTradgVol"):
        data[col] = pd.to_numeric(data[col], errors="coerce").replace(
            [float("inf"), float("-inf")], float("nan")
        )
    market_dates = sorted(data["Date"].unique())
    if len(market_dates) < 21:
        return pd.DataFrame([_wait(s) for s in candidates["TckrSymb"]], columns=_OUTPUT)

    counts = candidates["TckrSymb"].astype(str).str.strip().str.upper().value_counts()
    output = []
    for symbol in candidates["TckrSymb"]:
        key = str(symbol).strip().upper()
        if counts.get(key, 0) != 1:
            output.append(_wait(symbol))
            continue
        stock = data[data["TckrSymb"].astype(str).str.strip().str.upper().eq(key)].copy()
        stock = stock.sort_values("Date", kind="mergesort")
        if stock["Date"].duplicated().any():
            output.append(_wait(symbol))
            continue
        by_date = {row["Date"]: row for _, row in stock.iterrows()}
        if any(day not in by_date for day in market_dates):
            output.append(_wait(symbol))
            continue
        rows = [by_date[day] for day in market_dates]
        if any(not _valid_candle(row) for row in rows):
            # No partial-history substitution: malformed rows make the
            # historical event sequence and subsequent price path ambiguous.
            output.append(_wait(symbol))
            continue

        event = None
        for i in range(20, len(rows)):
            current = rows[i]
            prior20 = rows[i - 20:i]
            prior_volumes = [_number(row["TtlTradgVol"]) for row in prior20]
            average_volume = sum(prior_volumes) / 20.0
            if not math.isfinite(average_volume) or average_volume <= 0:
                continue
            current_volume = _number(current["TtlTradgVol"])
            rvol = current_volume / average_volume
            candle_range = _number(current["HghPric"]) - _number(current["LwPric"])
            if candle_range <= 0:
                continue
            clv = (_number(current["ClsPric"]) - _number(current["LwPric"])) / candle_range
            high20 = max(_number(row["HghPric"]) for row in prior20)
            close = _number(current["ClsPric"])
            qualifies20 = close > high20 and rvol >= 2.0 and clv > 0.75
            qualifies50 = False
            if i >= 50:
                prior50 = rows[i - 50:i]
                high50 = max(_number(row["HghPric"]) for row in prior50)
                qualifies50 = close > high50 and rvol >= 1.5 and clv > 0.75
            if qualifies20 or qualifies50:
                event = (i, high20 if qualifies20 else high50, current_volume)

        if event is None:
            row = _wait(symbol)
            row["RetestObservationStatus"] = "NO_PRIOR_BREAKOUT_EVENT_OBSERVED_IN_AVAILABLE_CACHE"
            row["ExactLevelTouchObserved"] = "NOT_OBSERVED"
            output.append(row)
            continue

        event_index, level, breakout_volume = event
        post = rows[event_index + 1:]
        touch_dates = [
            market_dates[event_index + 1 + j]
            for j, row in enumerate(post)
            if _number(row["LwPric"]) <= level <= _number(row["HghPric"])
        ]
        last_close = _number(post[-1]["ClsPric"]) if post else float("nan")
        lowest_low = min((_number(row["LwPric"]) for row in post), default=float("nan"))
        highest_high = max((_number(row["HghPric"]) for row in post), default=float("nan"))
        post_closes = [_number(row["ClsPric"]) for row in post]
        closes_above = sum(value > level for value in post_closes)
        closes_below = sum(value < level for value in post_closes)
        closes_at = sum(value == level for value in post_closes)
        post_volumes = [_number(row["TtlTradgVol"]) for row in post]
        post_avg_volume = (
            sum(post_volumes) / len(post_volumes)
            if post_volumes and all(math.isfinite(v) and v >= 0 for v in post_volumes)
            else float("nan")
        )
        output.append({
            "TckrSymb": symbol,
            "RetestObservationStatus": (
                "BREAKOUT_EVENT_CURRENT_SESSION_NO_POST_EVENT_OBSERVATIONS"
                if not post else "POST_BREAKOUT_PRICE_OBSERVATIONS_AVAILABLE"
            ),
            "LastBreakoutDate": market_dates[event_index].isoformat(),
            "BreakoutReferenceLevel": level,
            "SessionsSinceBreakout": len(post),
            "PostBreakoutLowestLow": lowest_low,
            "PostBreakoutHighestHigh": highest_high,
            "PostBreakoutLastClose": last_close,
            "PostBreakoutLowestLowVsLevelPct": (
                (lowest_low - level) / level * 100.0
                if post and level > 0 else float("nan")
            ),
            "PostBreakoutHighestHighVsLevelPct": (
                (highest_high - level) / level * 100.0
                if post and level > 0 else float("nan")
            ),
            "PostBreakoutClosesAboveLevelCount": closes_above if post else float("nan"),
            "PostBreakoutClosesBelowLevelCount": closes_below if post else float("nan"),
            "PostBreakoutClosesAtLevelCount": closes_at if post else float("nan"),
            "PostBreakoutCloseVsLevelPct": (
                (last_close - level) / level * 100.0
                if post and level > 0 else float("nan")
            ),
            "ExactLevelTouchObserved": bool(touch_dates) if post else "NOT_YET_OBSERVED",
            "FirstExactLevelTouchDate": touch_dates[0].isoformat() if touch_dates else None,
            "BreakoutDayVolume": breakout_volume,
            "PostBreakoutAverageVolume": post_avg_volume,
            "PostBreakoutVolumeVsBreakoutPct": (
                (post_avg_volume / breakout_volume - 1.0) * 100.0
                if post and math.isfinite(post_avg_volume) and breakout_volume > 0
                else float("nan")
            ),
        })
    return pd.DataFrame(output, columns=_OUTPUT)
