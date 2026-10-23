"""NSE V8 liquidity gate based on prior 20 complete EOD sessions.

Eligibility rule: mean daily traded value (NSE CM Bhavcopy TtlTrfVal, INR)
across 20 distinct prior sessions must be >= INR 2 crore. If a full 20-session
history or a valid traded-value observation is missing, status is WAIT_FOR_DATA.
This is a turnover-based liquidity proxy; it does not claim to validate bid-ask
spread or market depth, which are not present in the daily bhavcopy.
"""
from __future__ import annotations

import math
from typing import Iterable

import pandas as pd

MINIMUM_AVG_DAILY_TRADED_VALUE_INR = 20_000_000.0  # ₹2 crore (relaxed from ₹5 crore)
REQUIRED_LIQUIDITY_SESSIONS = 20
VALUE_COLUMN = "TtlTrfVal"


def apply_liquidity_filter(
    candidates: pd.DataFrame,
    historical: Iterable[pd.DataFrame],
    symbol_col: str = "TckrSymb",
    value_col: str = VALUE_COLUMN,
    minimum_average_daily_value: float = MINIMUM_AVG_DAILY_TRADED_VALUE_INR,
    required_sessions: int = REQUIRED_LIQUIDITY_SESSIONS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return only liquidity-qualified candidates plus a complete audit.

    Uses exactly the latest ``required_sessions`` historical frames; callers
    should pass prior sessions only (not the current EOD session). A symbol must
    have a valid non-negative traded value on every session to be evaluated.
    """
    history = list(historical)
    metric_columns = [
        "LiquiditySessions",
        "AvgDailyTradedValue20D",
        "MinimumAvgDailyTradedValueINR",
        "LiquidityStatus",
        "LiquidityFilterStatus",
    ]
    if candidates.empty:
        empty = candidates.copy()
        for col in metric_columns:
            empty[col] = pd.Series(dtype="object")
        return empty, empty.copy()
    if symbol_col not in candidates.columns:
        raise ValueError(f"Candidate symbol column missing: {symbol_col}")

    recent = history[-required_sessions:]
    schema_complete = len(recent) == required_sessions and all(
        symbol_col in frame.columns and value_col in frame.columns for frame in recent
    )
    session_maps: list[dict[str, float]] = []
    if schema_complete:
        for frame in recent:
            temp = frame[[symbol_col, value_col]].copy()
            temp[symbol_col] = temp[symbol_col].astype(str).str.strip().str.upper()
            temp[value_col] = pd.to_numeric(temp[value_col], errors="coerce")
            temp = temp.dropna(subset=[symbol_col, value_col])
            temp = temp[temp[value_col] >= 0]
            temp = temp.drop_duplicates(subset=[symbol_col], keep="last")
            session_maps.append(dict(zip(temp[symbol_col], temp[value_col].astype(float))))

    rows: list[dict] = []
    for _, candidate in candidates.iterrows():
        record = candidate.to_dict()
        symbol = str(candidate.get(symbol_col, "")).strip().upper()
        values = [mapping.get(symbol) for mapping in session_maps] if schema_complete else []
        valid = (
            schema_complete
            and len(values) == required_sessions
            and all(value is not None and math.isfinite(float(value)) for value in values)
        )
        average_value = float(sum(values) / required_sessions) if valid else float("nan")
        if not valid:
            status = "WAIT_FOR_DATA"
            session_count = sum(value is not None for value in values) if values else 0
        elif average_value >= float(minimum_average_daily_value):
            status = "PASS_GE_2CR_AVG_DAILY_VALUE"
            session_count = required_sessions
        else:
            status = "FILTERED_OUT_LT_2CR_AVG_DAILY_VALUE"
            session_count = required_sessions
        record.update({
            "LiquiditySessions": int(session_count),
            "AvgDailyTradedValue20D": average_value,
            "MinimumAvgDailyTradedValueINR": float(minimum_average_daily_value),
            "LiquidityStatus": status,
            "LiquidityFilterStatus": status,
        })
        rows.append(record)

    audit = pd.DataFrame(rows)
    qualified = audit[audit["LiquidityStatus"] == "PASS_GE_2CR_AVG_DAILY_VALUE"].copy()
    print(f"[LIQUIDITY] Threshold: average daily traded value >= ₹{minimum_average_daily_value:,.0f} over {required_sessions} prior sessions")
    print(f"[LIQUIDITY] PASS: {len(qualified)}; REJECT: {(audit['LiquidityStatus'] == 'FILTERED_OUT_LT_2CR_AVG_DAILY_VALUE').sum()}; WAIT_FOR_DATA: {(audit['LiquidityStatus'] == 'WAIT_FOR_DATA').sum()}")
    return qualified, audit
