"""Observation-only forward outcome tracker for NSE V8 signal snapshots.

Entry reference is the signal EOD close (research reference, not a fill).
Returns are raw price movement; fees/slippage remain NOT_CONFIGURED.
Only complete official-session horizons with valid OHLC are recorded.
"""
from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path
import math

import pandas as pd

from nse_trading_calendar import is_trading_session

OUTCOME_COLUMNS = [
    "EODDate", "TckrSymb", "HorizonSessions", "OutcomeStatus",
    "HorizonEndDate", "EntryReference", "EntryReferenceType",
    "CloseReturnPct", "MFE_Pct", "MAE_Pct", "ObservedSessionCount",
    "PriceSource", "FeesSlippageAssumption",
]
SIGNAL_OUTCOME_COLUMNS = ("Result5D", "Result10D", "Result20D", "MFE", "MAE")
ENTRY_REFERENCE_TYPE = "SIGNAL_EOD_CLOSE"
FEES_SLIPPAGE_ASSUMPTION = "NOT_CONFIGURED"


def _read_outcomes(path: Path) -> dict[tuple[str, str, int], dict]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != OUTCOME_COLUMNS:
            raise ValueError("signal_outcomes.csv schema mismatch")
        records = {}
        for row in reader:
            key = (row["EODDate"], row["TckrSymb"], int(row["HorizonSessions"]))
            if key in records:
                raise ValueError(f"duplicate immutable outcome key: {key}")
            records[key] = row
        return records


def _history_index(history_frames) -> tuple[dict[date, dict[str, dict]], list[date]]:
    by_date: dict[date, dict[str, dict]] = {}
    session_cache: dict[date, bool] = {}
    required = ["Date", "TckrSymb", "HghPric", "LwPric", "ClsPric"]
    for frame in history_frames or []:
        if frame is None or frame.empty or not set(required).issubset(frame.columns):
            continue
        # Avoid re-reading the official calendar once per symbol; one check per
        # distinct EOD date is sufficient for a full-market Bhavcopy frame.
        selected = frame.loc[:, required]
        for raw_date, raw_symbol, raw_high, raw_low, raw_close in selected.itertuples(index=False, name=None):
            day_value = pd.to_datetime(raw_date, errors="coerce")
            if pd.isna(day_value):
                continue
            day = day_value.date()
            if day not in session_cache:
                session_cache[day] = is_trading_session(day)
            if not session_cache[day]:
                continue
            symbol = str(raw_symbol).strip().upper()
            if not symbol:
                continue
            bucket = by_date.setdefault(day, {})
            if symbol in bucket:
                raise ValueError(f"duplicate Bhavcopy OHLC row for {day} {symbol}")
            values = {}
            for col, raw_value in (("HghPric", raw_high), ("LwPric", raw_low), ("ClsPric", raw_close)):
                try:
                    value = float(raw_value)
                except (TypeError, ValueError):
                    value = float("nan")
                values[col] = value
            bucket[symbol] = values
    return by_date, sorted(by_date)


def update_signal_outcomes(
    signal_log_path: str | Path,
    history_frames,
    *,
    outcome_store_path: str | Path = "data/signal_history/signal_outcomes.csv",
) -> dict[str, int]:
    """Append newly completed horizon observations and enrich the per-run CSV copy."""
    log_path = Path(signal_log_path)
    store_path = Path(outcome_store_path)
    if not log_path.exists():
        raise FileNotFoundError(log_path)
    by_date, available_dates = _history_index(history_frames)
    outcomes = _read_outcomes(store_path)
    with log_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("signal log header missing")
        rows = list(reader)
        columns = list(reader.fieldnames)
    missing_columns = [name for name in SIGNAL_OUTCOME_COLUMNS if name not in columns]
    if missing_columns:
        raise ValueError(f"signal log missing outcome columns: {missing_columns}")

    new_records = []
    completed = 0
    latest_available_date = max(available_dates) if available_dates else None
    for row in rows:
        signal_day = date.fromisoformat(row["EODDate"])
        symbol = str(row["TckrSymb"]).strip().upper()
        try:
            entry = float(row.get("ClsPric", ""))
        except (TypeError, ValueError):
            entry = float("nan")
        # Enumerate every official NSE session, not only dates represented by
        # downloaded Bhavcopy files. A missing whole-market file must leave the
        # affected horizon incomplete instead of shifting the horizon forward.
        future_sessions = []
        if latest_available_date is not None:
            cursor = signal_day + timedelta(days=1)
            while cursor <= latest_available_date:
                if is_trading_session(cursor):
                    future_sessions.append(cursor)
                cursor += timedelta(days=1)
        for horizon in (5, 10, 20):
            key = (signal_day.isoformat(), symbol, horizon)
            if key in outcomes or len(future_sessions) < horizon:
                continue
            horizon_days = future_sessions[:horizon]
            session_rows = [by_date.get(day, {}).get(symbol) for day in horizon_days]
            if not math.isfinite(entry) or entry <= 0 or any(item is None for item in session_rows):
                continue
            highs = [item["HghPric"] for item in session_rows]
            lows = [item["LwPric"] for item in session_rows]
            closes = [item["ClsPric"] for item in session_rows]
            if any(not math.isfinite(x) or x <= 0 for x in highs + lows + closes):
                continue
            if any(low > high for low, high in zip(lows, highs)):
                continue
            record = {
                "EODDate": signal_day.isoformat(),
                "TckrSymb": symbol,
                "HorizonSessions": str(horizon),
                "OutcomeStatus": "COMPLETE",
                "HorizonEndDate": horizon_days[-1].isoformat(),
                "EntryReference": f"{entry:.10g}",
                "EntryReferenceType": ENTRY_REFERENCE_TYPE,
                "CloseReturnPct": f"{(closes[-1] - entry) / entry * 100:.8f}",
                "MFE_Pct": f"{(max(highs) - entry) / entry * 100:.8f}",
                "MAE_Pct": f"{(min(lows) - entry) / entry * 100:.8f}",
                "ObservedSessionCount": str(horizon),
                "PriceSource": "VALIDATED_NSE_BHAVCOPY_OHLC",
                "FeesSlippageAssumption": FEES_SLIPPAGE_ASSUMPTION,
            }
            new_records.append(record)
            outcomes[key] = record
            completed += 1

    if new_records:
        store_path.parent.mkdir(parents=True, exist_ok=True)
        exists = store_path.exists() and store_path.stat().st_size > 0
        with store_path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=OUTCOME_COLUMNS)
            if not exists:
                writer.writeheader()
            writer.writerows(new_records)

    for row in rows:
        signal_day = row["EODDate"]
        symbol = str(row["TckrSymb"]).strip().upper()
        for horizon, column in ((5, "Result5D"), (10, "Result10D"), (20, "Result20D")):
            outcome = outcomes.get((signal_day, symbol, horizon))
            row[column] = outcome["CloseReturnPct"] if outcome else ""
        outcome20 = outcomes.get((signal_day, symbol, 20))
        row["MFE"] = outcome20["MFE_Pct"] if outcome20 else ""
        row["MAE"] = outcome20["MAE_Pct"] if outcome20 else ""

    with log_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return {"new_outcomes": len(new_records), "completed_horizons": completed, "signals": len(rows)}
