"""Append-only, observation-only EOD signal log.

This module never selects, filters, scores, or modifies scanner rows.
"""
from __future__ import annotations

import csv
import math
from pathlib import Path

import pandas as pd

SIGNAL_LOG_COLUMNS = [
    "EODDate", "TckrSymb", "EODWatchlistStatus", "DeliveryCategory",
    "LiquidityTier", "RVOL", "SetupType", "TrendClassification",
    "RelativeStrengthNifty", "V8Score", "EntryZoneLow", "EntryZoneHigh",
    "StopLoss", "Target/RiskReward", "StopDistancePct",
    "SectorStrengthStatus", "MarketRegimeStatus", "ClsPric",
    "Result5D", "Result10D", "Result20D", "MFE", "MAE",
]


def _blank(value) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(value, float) and not math.isfinite(value):
        return ""
    return str(value)


def _date_text(value) -> str:
    if value is None or _blank(value) == "":
        return ""
    try:
        return pd.Timestamp(value).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return _blank(value)


def _delivery_category(row) -> str:
    explicit = _blank(row.get("DeliveryCategory"))
    if explicit:
        return explicit
    a = _blank(row.get("DeliveryCategoryAStatus")).upper() == "PASS_AVG_GE_60_PERCENT"
    b = _blank(row.get("DeliveryCategoryBStatus")).upper() == "PASS_EACH_DAY_GE_60_PERCENT"
    if a and b:
        return "A_AND_B"
    if a:
        return "A_ONLY"
    if b:
        return "B_ONLY"
    if _blank(row.get("DeliveryFilterStatus")).upper() == "WAIT_FOR_DATA":
        return "WAIT_FOR_DATA"
    return ""


def _target_risk_reward(row) -> str:
    target = _blank(row.get("TargetPricePlan"))
    reward = _blank(row.get("RiskReward"))
    if target and reward:
        return f"{target} / {reward}R"
    return target or reward


def _signal_record(row, eod_date) -> dict[str, str]:
    entry = row.get("EntryPricePlan", row.get("EntryZoneHigh"))
    stop = row.get("StopLossPlan")
    try:
        entry_num = float(entry)
        stop_num = float(stop)
        distance = ((entry_num - stop_num) / entry_num) * 100 if entry_num > 0 and 0 < stop_num < entry_num else float("nan")
    except (TypeError, ValueError):
        distance = float("nan")
    record = {
        "EODDate": _date_text(eod_date),
        "TckrSymb": _blank(row.get("TckrSymb")).strip().upper(),
        "EODWatchlistStatus": _blank(row.get("EODWatchlistStatus")),
        "DeliveryCategory": _delivery_category(row),
        "LiquidityTier": _blank(row.get("LiquidityTier")),
        "RVOL": _blank(row.get("RVOL")),
        "SetupType": _blank(row.get("SetupType")),
        "TrendClassification": _blank(row.get("TrendClassification")),
        "RelativeStrengthNifty": _blank(row.get("RelativeStrengthNifty")),
        "V8Score": _blank(row.get("V8Score")),
        "EntryZoneLow": _blank(row.get("EntryZoneLow")),
        "EntryZoneHigh": _blank(row.get("EntryZoneHigh")),
        "StopLoss": _blank(stop),
        "Target/RiskReward": _target_risk_reward(row),
        "StopDistancePct": _blank(distance),
        "SectorStrengthStatus": _blank(row.get("SectorStrengthStatus")),
        "MarketRegimeStatus": _blank(row.get("MarketRegimeStatus")),
        "ClsPric": _blank(row.get("ClsPric")),
        "Result5D": "", "Result10D": "", "Result20D": "", "MFE": "", "MAE": "",
    }
    return record


def append_signal_log(result: pd.DataFrame, eod_date, path="outputs/signal_log.csv") -> int:
    """Append one row per EOD date/symbol; warn and continue on all write failures."""
    try:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        exists = target.exists() and target.stat().st_size > 0
        existing_keys = set()
        if exists:
            with target.open("r", newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                if reader.fieldnames != SIGNAL_LOG_COLUMNS:
                    raise ValueError("existing signal_log.csv header does not match the required schema")
                for old in reader:
                    existing_keys.add((_date_text(old.get("EODDate")), _blank(old.get("TckrSymb")).strip().upper()))
        new_rows = []
        seen = set(existing_keys)
        for _, row in result.iterrows():
            record = _signal_record(row, eod_date)
            key = (record["EODDate"], record["TckrSymb"])
            if not key[0] or not key[1] or key in seen:
                continue
            seen.add(key)
            new_rows.append(record)
        if not new_rows and exists:
            return 0
        with target.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=SIGNAL_LOG_COLUMNS, extrasaction="ignore")
            if not exists:
                writer.writeheader()
            if new_rows:
                writer.writerows(new_rows)
        return len(new_rows)
    except Exception as exc:
        print(f"[SIGNAL LOG] WARNING: could not append outputs/signal_log.csv; scan continues: {exc}")
        return 0
