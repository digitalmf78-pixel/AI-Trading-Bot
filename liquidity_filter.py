"""NSE V8 liquidity gate based on prior 20 complete EOD sessions.

Eligibility rule: mean daily traded value (NSE CM Bhavcopy TtlTrfVal, INR)
across 20 distinct prior sessions must be >= INR 1.5 crore. Qualified names are
tiered as low (₹1.5–2 crore), medium (₹2–5 crore), or strong (>=₹5 crore). Missing
sessions or values remain WAIT_FOR_DATA.
This is a turnover-based liquidity proxy; it does not claim to validate bid-ask
spread or market depth, which are not present in the daily bhavcopy.
"""
from __future__ import annotations

import math
from typing import Iterable

import pandas as pd

MINIMUM_AVG_DAILY_TRADED_VALUE_INR = 15_000_000.0  # ₹1.5 crore minimum, mildly relaxed from ₹2 crore
LOW_LIQUIDITY_MAX_INR = 20_000_000.0
MEDIUM_LIQUIDITY_MAX_INR = 50_000_000.0
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
        "LiquidityTier",
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
    # If session dates are supplied, verify that the 20 frames represent 20
    # distinct dates. Date-less legacy callers retain the documented ordered
    # session-list contract.
    date_flags = ["Date" in frame.columns for frame in recent]
    if schema_complete and any(date_flags):
        if not all(date_flags):
            schema_complete = False
        else:
            session_dates = []
            for frame in recent:
                parsed_dates = pd.to_datetime(frame["Date"], errors="coerce").dropna().dt.date.unique()
                if len(parsed_dates) != 1:
                    schema_complete = False
                    break
                session_dates.append(parsed_dates[0])
            if len(set(session_dates)) != required_sessions:
                schema_complete = False

    session_maps: list[dict[str, float]] = []
    if schema_complete:
        for frame in recent:
            temp = frame[[symbol_col, value_col]].copy()
            temp[symbol_col] = temp[symbol_col].astype(str).str.strip().str.upper()
            duplicate_symbols = set(
                temp.loc[temp[symbol_col].duplicated(keep=False), symbol_col].dropna()
            )
            # Ambiguous duplicate symbol rows must become missing data, not an
            # arbitrary keep-last selection that could pass the liquidity gate.
            if duplicate_symbols:
                temp = temp[~temp[symbol_col].isin(duplicate_symbols)]
            temp[value_col] = pd.to_numeric(temp[value_col], errors="coerce")
            temp = temp.dropna(subset=[symbol_col, value_col])
            temp = temp[temp[value_col] >= 0]
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
            if average_value < LOW_LIQUIDITY_MAX_INR:
                status, tier = "PASS_LOW_LIQUIDITY", "LOW"
            elif average_value < MEDIUM_LIQUIDITY_MAX_INR:
                status, tier = "PASS_MEDIUM_LIQUIDITY", "MEDIUM"
            else:
                status, tier = "PASS_STRONG_LIQUIDITY", "STRONG"
            session_count = required_sessions
        else:
            status, tier = "FILTERED_OUT_BELOW_MINIMUM", "BELOW_MINIMUM"
            session_count = required_sessions
        record.update({
            "LiquiditySessions": int(session_count),
            "AvgDailyTradedValue20D": average_value,
            "MinimumAvgDailyTradedValueINR": float(minimum_average_daily_value),
            "LiquidityStatus": status,
            "LiquidityFilterStatus": "PASS" if status.startswith("PASS_") else status,
            "LiquidityTier": tier if valid else "WAIT_FOR_DATA",
        })
        rows.append(record)

    audit = pd.DataFrame(rows)
    qualified = audit[audit["LiquidityStatus"].astype(str).str.startswith("PASS_")].copy()
    print(f"[LIQUIDITY] Minimum ₹{minimum_average_daily_value:,.0f}; LOW ₹1.5–2cr, MEDIUM ₹2–5cr, STRONG >=₹5cr over {required_sessions} prior sessions")
    print(f"[LIQUIDITY] PASS={len(qualified)} tiers={qualified.get('LiquidityTier', pd.Series(dtype=str)).value_counts().to_dict()}; REJECT={audit['LiquidityStatus'].astype(str).str.startswith('FILTERED_OUT').sum()}; WAIT_FOR_DATA={(audit['LiquidityStatus'] == 'WAIT_FOR_DATA').sum()}")
    return qualified, audit

