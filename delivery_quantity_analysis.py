"""Point-in-time NSE Delivery Quantity and price-response observations.

This module is deliberately observational: it does not qualify/reject stocks,
rank them, or claim institutional accumulation. Missing/ambiguous values are
reported as WAIT_FOR_DATA. No unapproved numeric thresholds are used.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
import math
import pandas as pd

OUTPUT_DIR = Path("outputs")
WINDOWS = (5, 10, 20)

ALIASES = {
    "symbol": ("SYMBOL", "TCKRSYMB"),
    "series": ("SERIES", "SCTYSRS"),
    "delivery_qty": (
        "DELIV_QTY", "DELIVERY_QTY", "DELIVQTY", "TTL_DLVRY_QTY",
        "TTLDLVRYQTY", "TTL_DELIV_QTY", "TOTAL_DELIVERY_QTY", "TTLDLVRYQTY",
    ),
    "delivery_pct": ("DELIV_PER", "DELIVERY_PERCENT", "DELIVPERC"),
    "traded_volume": ("TTL_TRD_QNTY", "TTLTRDQNTY", "TOTAL_TRADED_QTY", "TtlTradgVol"),
    "close": ("CLOSE_PRICE", "CLOSEPRICE", "ClsPric", "CLOSE"),
}


def _column(frame: pd.DataFrame, aliases: tuple[str, ...]) -> str | None:
    lookup = {str(col).strip().upper().replace(" ", "_"): col for col in frame.columns}
    for alias in aliases:
        key = alias.strip().upper().replace(" ", "_")
        if key in lookup:
            return lookup[key]
    return None


def _date(value) -> date | None:
    parsed = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else parsed.date()


def _slope(values: list[float]) -> float:
    # OLS slope against equally spaced session indices; descriptive only.
    n = len(values)
    if n < 2:
        return float("nan")
    x_mean = (n - 1) / 2
    y_mean = sum(values) / n
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    if denominator == 0:
        return float("nan")
    return sum((i - x_mean) * (value - y_mean) for i, value in enumerate(values)) / denominator


def _pct_change(first: float, last: float) -> float:
    if not math.isfinite(first) or first == 0 or not math.isfinite(last):
        return float("nan")
    return (last / first - 1.0) * 100.0


def build_delivery_quantity_report(
    candidates: pd.DataFrame,
    asof_date,
    sessions: list[tuple[date, pd.DataFrame]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Enrich candidates with 5/10/20-session quantity and price observations.

    Uses the latest distinct supplied report dates on/before as-of date. A
    symbol/window is complete only when every selected session has exactly one
    valid EQ/series observation with non-negative Delivery Quantity.
    """
    if candidates is None:
        candidates = pd.DataFrame()
    frame = candidates.copy()
    if frame.empty:
        return frame, frame.copy()
    if "TckrSymb" not in frame.columns:
        raise ValueError("Candidates must contain TckrSymb")

    asof = _date(asof_date)
    if asof is None:
        raise ValueError(f"Invalid as-of date: {asof_date!r}")

    by_day: dict[date, pd.DataFrame] = {}
    for raw_day, raw in sessions:
        day = _date(raw_day)
        if day is None or day > asof or day in by_day or raw is None or raw.empty:
            continue
        by_day[day] = raw.copy()
    ordered_days = sorted(by_day)
    report_frames: dict[date, pd.DataFrame] = {}
    schema_errors: dict[date, str] = {}
    for day in ordered_days:
        raw = by_day[day]
        sym_col = _column(raw, ALIASES["symbol"])
        ser_col = _column(raw, ALIASES["series"])
        qty_col = _column(raw, ALIASES["delivery_qty"])
        pct_col = _column(raw, ALIASES["delivery_pct"])
        vol_col = _column(raw, ALIASES["traded_volume"])
        close_col = _column(raw, ALIASES["close"])
        if sym_col is None or ser_col is None or qty_col is None:
            schema_errors[day] = "DELIVERY_QUANTITY_COLUMN_OR_SECURITY_KEY_MISSING"
            continue
        data = pd.DataFrame({
            "SYMBOL": raw[sym_col].astype(str).str.strip().str.upper(),
            "SERIES": raw[ser_col].astype(str).str.strip().str.upper(),
            "DELIVERY_QTY": pd.to_numeric(raw[qty_col], errors="coerce"),
            "DELIVERY_PCT": pd.to_numeric(raw[pct_col], errors="coerce") if pct_col else float("nan"),
            "TRADED_VOLUME": pd.to_numeric(raw[vol_col], errors="coerce") if vol_col else float("nan"),
            "CLOSE_PRICE": pd.to_numeric(raw[close_col], errors="coerce") if close_col else float("nan"),
        })
        data = data[data["SYMBOL"].ne("") & data["SYMBOL"].str.lower().ne("nan")]
        data = data[data["DELIVERY_QTY"].ge(0)]
        report_frames[day] = data

    audit_rows = []
    for _, candidate in frame.iterrows():
        symbol = str(candidate.get("TckrSymb", "")).strip().upper()
        series = str(candidate.get("SctySrs", "EQ")).strip().upper()
        if not series or series.lower() == "nan":
            series = "EQ"
        record = candidate.to_dict()
        all_values: dict[date, dict] = {}
        duplicate_dates: list[str] = []
        for day in ordered_days:
            data = report_frames.get(day)
            if data is None:
                continue
            match = data[(data["SYMBOL"] == symbol) & (data["SERIES"] == series)]
            if len(match) > 1:
                duplicate_dates.append(day.isoformat())
                continue
            if len(match) == 1:
                all_values[day] = match.iloc[0].to_dict()

        for window in WINDOWS:
            prefix = f"DeliveryQty{window}D"
            window_days = ordered_days[-window:]
            values = [all_values.get(day) for day in window_days]
            complete = (
                len(window_days) == window
                and all(value is not None for value in values)
                and not duplicate_dates
                and not any(day in schema_errors for day in window_days)
            )
            record[f"{prefix}Sessions"] = sum(value is not None for value in values)
            record[f"{prefix}Status"] = "COMPLETE" if complete else "WAIT_FOR_DATA"
            if not complete:
                record[f"{prefix}Reason"] = (
                    "AMBIGUOUS_DUPLICATE_SYMBOL_SERIES"
                    if duplicate_dates else
                    "DELIVERY_QUANTITY_SCHEMA_MISSING"
                    if any(day in schema_errors for day in window_days) else
                    "INSUFFICIENT_OR_MISSING_SYMBOL_SESSION_DATA"
                )
                for suffix in ("Total", "Average", "First", "Last", "ChangePct", "SlopePerSession",
                               "DeliveryPctAverage", "TradedVolumeAverage", "CloseFirst", "CloseLast",
                               "CloseChangePct", "CloseRangePct"):
                    record[f"{prefix}{suffix}"] = float("nan")
                continue

            qty = [float(value["DELIVERY_QTY"]) for value in values]
            record[f"{prefix}Reason"] = "OK"
            record[f"{prefix}Total"] = sum(qty)
            record[f"{prefix}Average"] = sum(qty) / window
            record[f"{prefix}First"] = qty[0]
            record[f"{prefix}Last"] = qty[-1]
            record[f"{prefix}ChangePct"] = _pct_change(qty[0], qty[-1])
            record[f"{prefix}SlopePerSession"] = _slope(qty)
            pct_values = [float(v["DELIVERY_PCT"]) for v in values if pd.notna(v["DELIVERY_PCT"])]
            volume_values = [float(v["TRADED_VOLUME"]) for v in values if pd.notna(v["TRADED_VOLUME"])]
            close_values = [float(v["CLOSE_PRICE"]) for v in values if pd.notna(v["CLOSE_PRICE"])]
            record[f"{prefix}DeliveryPctAverage"] = sum(pct_values) / len(pct_values) if len(pct_values) == window else float("nan")
            record[f"{prefix}TradedVolumeAverage"] = sum(volume_values) / len(volume_values) if len(volume_values) == window else float("nan")
            record[f"{prefix}CloseFirst"] = close_values[0] if len(close_values) == window else float("nan")
            record[f"{prefix}CloseLast"] = close_values[-1] if len(close_values) == window else float("nan")
            record[f"{prefix}CloseChangePct"] = _pct_change(close_values[0], close_values[-1]) if len(close_values) == window else float("nan")
            record[f"{prefix}CloseRangePct"] = (
                (max(close_values) - min(close_values)) / close_values[0] * 100.0
                if len(close_values) == window and close_values[0] > 0 else float("nan")
            )
            for day, value in zip(window_days, values):
                record[f"DeliveryQty_{day.strftime('%Y%m%d')}"] = value["DELIVERY_QTY"]
                record[f"DeliveryPct_{day.strftime('%Y%m%d')}"] = value["DELIVERY_PCT"]
                record[f"TradedVolume_{day.strftime('%Y%m%d')}"] = value["TRADED_VOLUME"]
                record[f"ClosePrice_{day.strftime('%Y%m%d')}"] = value["CLOSE_PRICE"]

        record["DeliveryQuantityStatus"] = (
            "COMPLETE_5_10_20D" if all(record[f"DeliveryQty{w}DStatus"] == "COMPLETE" for w in WINDOWS)
            else "WAIT_FOR_DATA"
        )
        record["DeliveryQuantityAsOfDate"] = asof.isoformat()
        record["DeliveryQuantitySourceDates"] = ",".join(day.isoformat() for day in ordered_days)
        audit_rows.append(record)

    audit = pd.DataFrame(audit_rows)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    audit.to_csv(OUTPUT_DIR / f"v8_delivery_quantity_observations_{asof:%Y%m%d}.csv", index=False)
    return audit.copy(), audit
