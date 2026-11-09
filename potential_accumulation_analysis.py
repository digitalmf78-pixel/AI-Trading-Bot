"""Independent potential-accumulation evidence observations.

This report is descriptive only. It never filters, scores, ranks or labels a
stock as institutionally accumulated. All thresholds are inherited only from
the existing Delivery >=60% observation and the existing 3-left/3-right pivot
definition. No new acceptance thresholds are introduced.
"""
from __future__ import annotations

from datetime import date
import math
from pathlib import Path
import pandas as pd

OUTPUT_DIR = Path("outputs")
RANGE_WINDOWS = (20, 50, 100, 200)
DELIVERY_OBSERVATION_THRESHOLD = 60.0


def _num(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else float("nan")
    except (TypeError, ValueError):
        return float("nan")


def _find_col(frame, names):
    lookup = {str(col).strip().upper().replace(" ", "_"): col for col in frame.columns}
    for name in names:
        key = name.strip().upper().replace(" ", "_")
        if key in lookup:
            return lookup[key]
    return None


def _pivots(values, left=3, right=3, high=False):
    points = []
    for i in range(left, len(values) - right):
        value = _num(values[i])
        window = [_num(v) for v in values[i-left:i+right+1]]
        if not math.isfinite(value) or any(not math.isfinite(v) for v in window):
            continue
        peers = window[:left] + window[left+1:]
        if high:
            if value >= max(window) and value > min(window[:left]) and value > min(window[left+1:]):
                points.append((i, value))
        else:
            if value <= min(window) and value < max(window[:left]) and value < max(window[left+1:]):
                points.append((i, value))
    return points


def _session_date(value):
    parsed = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else parsed.date()


def _build_price_history(candidate, historical, asof, market_sessions):
    symbol = str(candidate.get("TckrSymb", "")).strip().upper()
    series = str(candidate.get("SctySrs", "EQ")).strip().upper() or "EQ"
    frames = []
    for raw in historical or []:
        if raw is None or raw.empty or "TckrSymb" not in raw.columns or "Date" not in raw.columns:
            continue
        part = raw[raw["TckrSymb"].astype(str).str.strip().str.upper().eq(symbol)].copy()
        if "SctySrs" in part.columns:
            part = part[part["SctySrs"].astype(str).str.strip().str.upper().eq(series)]
        if not part.empty:
            frames.append(part)
    current = candidate.to_dict()
    current["TckrSymb"] = symbol
    current["SctySrs"] = series
    current["Date"] = pd.Timestamp(asof)
    frames.append(pd.DataFrame([current]))
    history = pd.concat(frames, ignore_index=True, sort=False)
    history["Date"] = pd.to_datetime(history["Date"], errors="coerce")
    history = history.dropna(subset=["Date"])
    history = history[history["Date"].dt.date <= asof]
    history = history.sort_values("Date", kind="mergesort")
    history = history.drop_duplicates(["TckrSymb", "Date"], keep="last")
    for col in ("OpnPric", "HghPric", "LwPric", "ClsPric", "TtlTradgVol"):
        if col in history.columns:
            history[col] = pd.to_numeric(history[col], errors="coerce")
    return history.dropna(subset=["ClsPric"]).reset_index(drop=True), market_sessions

def _delivery_observations(symbol, series, sessions, asof):
    observations = []
    for raw_day, raw in sessions or []:
        day = _session_date(raw_day)
        if day is None or day > asof or raw is None or raw.empty:
            continue
        sym_col = _find_col(raw, ("SYMBOL", "TckrSymb"))
        ser_col = _find_col(raw, ("SERIES", "SctySrs"))
        qty_col = _find_col(raw, ("DELIV_QTY", "DELIVERY_QTY", "DELIVQTY"))
        pct_col = _find_col(raw, ("DELIV_PER", "DELIVERY_PERCENT"))
        close_col = _find_col(raw, ("CLOSE_PRICE", "ClsPric"))
        prev_col = _find_col(raw, ("PREV_CLOSE", "PrvsClsgPric"))
        open_col = _find_col(raw, ("OPEN_PRICE", "OpnPric"))
        high_col = _find_col(raw, ("HIGH_PRICE", "HghPric"))
        low_col = _find_col(raw, ("LOW_PRICE", "LwPric"))
        vol_col = _find_col(raw, ("TTL_TRD_QNTY", "TtlTradgVol"))
        if not all((sym_col, ser_col, qty_col, pct_col)):
            continue
        data = raw.copy()
        data["_SYM"] = data[sym_col].astype(str).str.strip().str.upper()
        data["_SER"] = data[ser_col].astype(str).str.strip().str.upper()
        match = data[(data["_SYM"] == symbol) & (data["_SER"] == series)]
        if len(match) != 1:
            continue
        row = match.iloc[0]
        qty, pct = _num(row[qty_col]), _num(row[pct_col])
        if not math.isfinite(qty) or qty < 0 or not math.isfinite(pct) or not 0 <= pct <= 100:
            continue
        close = _num(row[close_col]) if close_col else float("nan")
        previous = _num(row[prev_col]) if prev_col else float("nan")
        high = _num(row[high_col]) if high_col else float("nan")
        low = _num(row[low_col]) if low_col else float("nan")
        volume = _num(row[vol_col]) if vol_col else float("nan")
        open_price = _num(row[open_col]) if open_col else float("nan")
        close_change = (close / previous - 1.0) * 100.0 if close > 0 and previous > 0 else float("nan")
        intraday_range = (high - low) / previous * 100.0 if high >= low >= 0 and previous > 0 else float("nan")
        observations.append({
            "Date": day, "DeliveryQty": qty, "DeliveryPct": pct,
            "TradedVolume": volume, "Open": open_price, "High": high,
            "Low": low, "Close": close, "PreviousClose": previous,
            "CloseChangePct": close_change, "IntradayRangePct": intraday_range,
        })
    return sorted(observations, key=lambda row: row["Date"])


def build_potential_accumulation_report(
    candidates: pd.DataFrame,
    historical,
    delivery_sessions,
    asof_date,
) -> pd.DataFrame:
    """Create non-gating quantity/price/base/supply observations for A/B names."""
    if candidates is None or candidates.empty:
        return pd.DataFrame()
    asof = _session_date(asof_date)
    if asof is None:
        raise ValueError(f"Invalid as-of date: {asof_date!r}")
    market_sessions = set()
    for raw in historical or []:
        if raw is None or raw.empty or "Date" not in raw.columns:
            continue
        for value in pd.to_datetime(raw["Date"], errors="coerce").dropna():
            day = value.date()
            if day <= asof:
                market_sessions.add(day)
    market_sessions.add(asof)
    ordered_market_sessions = sorted(market_sessions)

    rows = []
    for _, candidate in candidates.drop_duplicates("TckrSymb", keep="first").iterrows():
        symbol = str(candidate.get("TckrSymb", "")).strip().upper()
        series = str(candidate.get("SctySrs", "EQ")).strip().upper() or "EQ"
        hist, _ = _build_price_history(candidate, historical, asof, ordered_market_sessions)
        row = {
            "TckrSymb": symbol, "AsOfDate": asof.isoformat(),
            "DeliveryCategory": candidate.get("DeliveryCategory", "UNKNOWN"),
            "RVOLBand": candidate.get("RVOLBand", "WAIT_FOR_DATA"),
            "PriceHistorySessions": len(hist),
            "PriceHistoryStatus": "WAIT_FOR_DATA",
            "DeliveryEvidenceStatus": "WAIT_FOR_DATA",
            "HighDeliverySessionCount": 0,
            "HighDeliveryQtyTotal": float("nan"),
            "HighDeliveryQtyAverage": float("nan"),
            "HighDeliveryPriceChangeAbsAveragePct": float("nan"),
            "HighDeliveryPriceChangeAbsMedianPct": float("nan"),
            "HighDeliveryIntradayRangeAveragePct": float("nan"),
            "HighDeliveryUpDayCount": 0,
            "HighDeliveryDownDayCount": 0,
            "DownDayCount20D": float("nan"), "UpDayCount20D": float("nan"),
            "DownDayVolumeAverage20D": float("nan"),
            "UpDayVolumeAverage20D": float("nan"),
            "DownVsUpVolumeRatio20D": float("nan"),
            "ConfirmedPivotLowCount": 0, "ConfirmedPivotHighCount": 0,
            "LatestPivotLow": float("nan"), "PreviousPivotLow": float("nan"),
            "LatestPivotLowDate": "", "PreviousPivotLowDate": "",
            "HigherLowStatus": "WAIT_FOR_DATA",
        }
        if not hist.empty:
            lows = hist["LwPric"].tolist() if "LwPric" in hist.columns else []
            highs = hist["HghPric"].tolist() if "HghPric" in hist.columns else []
            low_pivots = _pivots(lows) if len(lows) >= 7 else []
            high_pivots = _pivots(highs, high=True) if len(highs) >= 7 else []
            row["ConfirmedPivotLowCount"] = len(low_pivots)
            row["ConfirmedPivotHighCount"] = len(high_pivots)
            if low_pivots:
                idx, value = low_pivots[-1]
                row["LatestPivotLow"] = value
                row["LatestPivotLowDate"] = hist.iloc[idx]["Date"].date().isoformat()
            if len(low_pivots) >= 2:
                idx, value = low_pivots[-2]
                row["PreviousPivotLow"] = value
                row["PreviousPivotLowDate"] = hist.iloc[idx]["Date"].date().isoformat()
                row["HigherLowStatus"] = "HIGHER_LOW_OBSERVED" if low_pivots[-1][1] > value else "NO_HIGHER_LOW_OBSERVED"
            elif len(low_pivots) == 1:
                row["HigherLowStatus"] = "WAIT_FOR_SECOND_CONFIRMED_PIVOT"

            for window in RANGE_WINDOWS:
                prefix = f"PriceRange{window}D"
                if len(hist) < window or "HghPric" not in hist.columns or "LwPric" not in hist.columns:
                    row[f"{prefix}Status"] = "WAIT_FOR_DATA"
                    for suffix in ("High", "Low", "WidthPct", "SessionsSinceLow", "SessionsSinceHigh", "ExactLowTouchCount", "ExactHighTouchCount"):
                        row[f"{prefix}{suffix}"] = float("nan")
                    continue
                window_dates = ordered_market_sessions[-window:]
                part = hist[hist["Date"].dt.date.isin(window_dates)].copy()
                if len(window_dates) != window or len(part) != window or part[["HghPric", "LwPric"]].isna().any().any():
                    row[f"{prefix}Status"] = "WAIT_FOR_DATA"
                    for suffix in ("High", "Low", "WidthPct", "SessionsSinceLow", "SessionsSinceHigh", "ExactLowTouchCount", "ExactHighTouchCount"):
                        row[f"{prefix}{suffix}"] = float("nan")
                    continue
                part = part.sort_values("Date")
                range_high = _num(part["HghPric"].max())
                range_low = _num(part["LwPric"].min())
                high_positions = [i for i, v in enumerate(part["HghPric"].tolist()) if _num(v) == range_high]
                low_positions = [i for i, v in enumerate(part["LwPric"].tolist()) if _num(v) == range_low]
                row[f"{prefix}Status"] = "OBSERVATION_AVAILABLE"
                row[f"{prefix}High"] = range_high
                row[f"{prefix}Low"] = range_low
                row[f"{prefix}WidthPct"] = (range_high / range_low - 1.0) * 100.0 if range_low > 0 else float("nan")
                row[f"{prefix}SessionsSinceLow"] = window - 1 - low_positions[-1]
                row[f"{prefix}SessionsSinceHigh"] = window - 1 - high_positions[-1]
                row[f"{prefix}ExactLowTouchCount"] = len(low_positions)
                row[f"{prefix}ExactHighTouchCount"] = len(high_positions)

            row["PriceHistoryStatus"] = (
                "COMPLETE_20D" if row.get("PriceRange20DStatus") == "OBSERVATION_AVAILABLE"
                else "WAIT_FOR_DATA"
            )

            recent_dates = ordered_market_sessions[-20:]
            recent = hist[hist["Date"].dt.date.isin(recent_dates)].copy().sort_values("Date")
            if len(recent_dates) == 20 and len(recent) == 20 and recent["ClsPric"].notna().all():
                recent["CloseReturnPct"] = recent["ClsPric"].pct_change() * 100.0
            else:
                recent = pd.DataFrame()
            if "TtlTradgVol" in recent.columns:
                recent["TtlTradgVol"] = pd.to_numeric(recent["TtlTradgVol"], errors="coerce")
            if not recent.empty:
                down = recent[recent["CloseReturnPct"] < 0]
                up = recent[recent["CloseReturnPct"] > 0]
                down_avg = down["TtlTradgVol"].mean() if "TtlTradgVol" in down.columns else float("nan")
                up_avg = up["TtlTradgVol"].mean() if "TtlTradgVol" in up.columns else float("nan")
                row["DownDayCount20D"] = len(down)
                row["UpDayCount20D"] = len(up)
                row["DownDayVolumeAverage20D"] = down_avg
                row["UpDayVolumeAverage20D"] = up_avg
                row["DownVsUpVolumeRatio20D"] = down_avg / up_avg if pd.notna(down_avg) and pd.notna(up_avg) and up_avg > 0 else float("nan")

        delivery_rows = _delivery_observations(symbol, series, delivery_sessions, asof)
        if len(delivery_rows) >= 5:
            row["DeliveryEvidenceStatus"] = "OBSERVATIONS_AVAILABLE"
            high_delivery = [item for item in delivery_rows if item["DeliveryPct"] >= DELIVERY_OBSERVATION_THRESHOLD]
            row["HighDeliverySessionCount"] = len(high_delivery)
            row["HighDeliveryQtyTotal"] = sum(item["DeliveryQty"] for item in high_delivery)
            row["HighDeliveryQtyAverage"] = row["HighDeliveryQtyTotal"] / len(high_delivery) if high_delivery else 0.0
            abs_changes = [abs(item["CloseChangePct"]) for item in high_delivery if math.isfinite(item["CloseChangePct"])]
            ranges = [item["IntradayRangePct"] for item in high_delivery if math.isfinite(item["IntradayRangePct"])]
            row["HighDeliveryPriceChangeAbsAveragePct"] = sum(abs_changes) / len(abs_changes) if abs_changes else float("nan")
            row["HighDeliveryPriceChangeAbsMedianPct"] = float(pd.Series(abs_changes).median()) if abs_changes else float("nan")
            row["HighDeliveryIntradayRangeAveragePct"] = sum(ranges) / len(ranges) if ranges else float("nan")
            row["HighDeliveryUpDayCount"] = sum(item["CloseChangePct"] > 0 for item in high_delivery if math.isfinite(item["CloseChangePct"]))
            row["HighDeliveryDownDayCount"] = sum(item["CloseChangePct"] < 0 for item in high_delivery if math.isfinite(item["CloseChangePct"]))
        else:
            row["DeliveryEvidenceStatus"] = "WAIT_FOR_DATA"
        row["EvidenceStatus"] = (
            "OBSERVATIONS_AVAILABLE" if row["PriceHistoryStatus"] == "COMPLETE_20D" and row["DeliveryEvidenceStatus"] == "OBSERVATIONS_AVAILABLE"
            else "PARTIAL_DATA"
        )
        rows.append(row)

    report = pd.DataFrame(rows)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report.to_csv(OUTPUT_DIR / f"v8_potential_accumulation_observations_{asof:%Y%m%d}.csv", index=False)
    return report
