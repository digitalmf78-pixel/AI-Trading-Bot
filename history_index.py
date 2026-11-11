"""Shared, one-pass indexing for historical NSE Bhavcopy rows.

This module changes lookup cost only. It deliberately preserves duplicate
symbol/session rows so downstream completeness checks can still return
WAIT_FOR_DATA instead of silently accepting ambiguous source data.
"""
from __future__ import annotations

import pandas as pd
from nse_trading_calendar import CalendarCoverageError, is_trading_session


def build_price_history_index(historical, asof):
    """Index all historical frames once by (symbol, series), preserving rows."""
    asof_day = pd.Timestamp(asof).date()
    frames = []
    market_dates = set()
    for raw in historical or []:
        if raw is None or raw.empty or "TckrSymb" not in raw.columns or "Date" not in raw.columns:
            continue
        part = raw.copy()
        part["Date"] = pd.to_datetime(part["Date"], errors="coerce")
        part = part.dropna(subset=["Date"])
        part = part[part["Date"].dt.date <= asof_day].copy()
        if part.empty:
            continue
        market_dates.update(value.date() for value in part["Date"])
        part["_HISTORY_SYMBOL"] = part["TckrSymb"].astype(str).str.strip().str.upper()
        if "SctySrs" in part.columns:
            part["_HISTORY_SERIES"] = part["SctySrs"].astype(str).str.strip().str.upper()
        else:
            part["_HISTORY_SERIES"] = "*"
        frames.append(part)

    if market_dates:
        first_observed = min(market_dates)
        try:
            expected_dates = [
                day.date()
                for day in pd.date_range(first_observed, asof_day, freq="D")
                if is_trading_session(day.date())
            ]
        except CalendarCoverageError:
            # Unknown/missing calendar coverage must never be inferred from
            # observed Bhavcopy dates. Empty dates force all windows to WAIT.
            expected_dates = []
        market_dates = set(expected_dates)
    else:
        market_dates = set()

    if not frames:
        return {}, sorted(market_dates)

    combined = pd.concat(frames, ignore_index=True, sort=False)
    index = {}
    for key, group in combined.groupby(["_HISTORY_SYMBOL", "_HISTORY_SERIES"], sort=False, dropna=False):
        symbol, series = key
        index[(str(symbol), str(series))] = (
            group.drop(columns=["_HISTORY_SYMBOL", "_HISTORY_SERIES"])
            .reset_index(drop=True)
        )
    return index, sorted(market_dates)


def candidate_price_history(history_index, candidate, asof):
    """Reproduce the prior per-candidate history merge without collapsing duplicates."""
    symbol = str(candidate.get("TckrSymb", "")).strip().upper()
    series = str(candidate.get("SctySrs", "EQ")).strip().upper() or "EQ"
    history = history_index.get((symbol, series))
    if history is None:
        history = history_index.get((symbol, "*"))
    if history is None:
        history = pd.DataFrame(columns=["TckrSymb", "SctySrs", "Date"])
    else:
        history = history.copy()

    history["Date"] = pd.to_datetime(history["Date"], errors="coerce")
    history = history.dropna(subset=["Date"])
    asof_day = pd.Timestamp(asof).date()
    history = history[history["Date"].dt.date <= asof_day]
    current = candidate.to_dict()
    current.update({"TckrSymb": symbol, "SctySrs": series, "Date": pd.Timestamp(asof)})
    existing_current = history[history["Date"].dt.date.eq(asof_day)]
    if len(existing_current) == 1:
        base = existing_current.iloc[0].to_dict()
        for key, value in current.items():
            if value is not None and not pd.isna(value):
                base[key] = value
        history = history[~history.index.isin(existing_current.index)]
        history = pd.concat([history, pd.DataFrame([base])], ignore_index=True, sort=False)
    elif len(existing_current) == 0:
        history = pd.concat([history, pd.DataFrame([current])], ignore_index=True, sort=False)

    history = history.sort_values("Date", kind="mergesort")
    for column in ("OpnPric", "HghPric", "LwPric", "ClsPric", "TtlTradgVol"):
        if column in history.columns:
            history[column] = pd.to_numeric(history[column], errors="coerce")
    return history.reset_index(drop=True)
