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
from history_index import build_price_history_index, candidate_price_history

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


def _atr14(history):
    if len(history) < 15 or not {"HghPric", "LwPric", "ClsPric"}.issubset(history.columns):
        return float("nan")
    recent = history.tail(15).copy()
    for column in ("HghPric", "LwPric", "ClsPric"):
        recent[column] = pd.to_numeric(recent[column], errors="coerce")
    if recent[["HghPric", "LwPric", "ClsPric"]].isna().any().any():
        return float("nan")
    if (
        (recent["HghPric"] < recent["LwPric"]).any()
        or (recent[["HghPric", "LwPric", "ClsPric"]] <= 0).any().any()
    ):
        return float("nan")
    previous = recent["ClsPric"].shift(1)
    true_range = pd.concat(
        [
            recent["HghPric"] - recent["LwPric"],
            (recent["HghPric"] - previous).abs(),
            (recent["LwPric"] - previous).abs(),
        ],
        axis=1,
    ).max(axis=1)
    value = true_range.iloc[1:].mean()
    return _num(value)


def _ema_window_observation(hist, market_dates, period):
    if len(market_dates) < period or len(hist) != len(market_dates):
        return {"status": "WAIT_FOR_DATA"}
    ordered = hist.sort_values("Date").copy()
    if "ClsPric" not in ordered.columns or ordered["ClsPric"].isna().any():
        return {"status": "WAIT_FOR_DATA"}
    close = pd.to_numeric(ordered["ClsPric"], errors="coerce")
    if close.isna().any():
        return {"status": "WAIT_FOR_DATA"}
    # Calculate the EMA over the entire available point-in-time history,
    # not merely the last N rows; N is the EMA span, not its seed window.
    ema_series = close.ewm(span=period, adjust=False, min_periods=period).mean()
    value = _num(ema_series.iloc[-1])
    current = _num(close.iloc[-1])
    if not math.isfinite(value) or value <= 0 or not math.isfinite(current):
        return {"status": "WAIT_FOR_DATA"}
    distance = (current / value - 1.0) * 100.0
    position = "ABOVE" if current > value else "BELOW" if current < value else "AT"
    return {"status": "COMPLETE", "value": value, "distance_pct": distance, "position": position}

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
        raw_dates = pd.to_datetime(raw["Date"], errors="coerce")
        part = raw[
            raw["TckrSymb"].astype(str).str.strip().str.upper().eq(symbol)
            & raw_dates.dt.date.le(asof)
        ].copy()
        if "SctySrs" in part.columns:
            part = part[part["SctySrs"].astype(str).str.strip().str.upper().eq(series)]
        if not part.empty:
            frames.append(part)
    history = (
        pd.concat(frames, ignore_index=True, sort=False)
        if frames else pd.DataFrame(columns=["TckrSymb", "SctySrs", "Date"])
    )
    history["Date"] = pd.to_datetime(history["Date"], errors="coerce")
    history = history.dropna(subset=["Date"])
    history = history[history["Date"].dt.date <= asof]
    current = candidate.to_dict()
    current["TckrSymb"] = symbol
    current["SctySrs"] = series
    current["Date"] = pd.Timestamp(asof)
    existing_current = history[history["Date"].dt.date.eq(asof)]
    if len(existing_current) == 1:
        # Merge the current candidate's non-null values into the single EOD
        # row already cached for this same session. This preserves full OHLC
        # fields without creating a false duplicate current-session record.
        base = existing_current.iloc[0].to_dict()
        for key, value in current.items():
            if value is not None and not pd.isna(value):
                base[key] = value
        history = history[~history.index.isin(existing_current.index)]
        history = pd.concat([history, pd.DataFrame([base])], ignore_index=True, sort=False)
    elif len(existing_current) == 0:
        history = pd.concat([history, pd.DataFrame([current])], ignore_index=True, sort=False)
    # If multiple cached rows already exist for the current session, keep all
    # of them visible; downstream exact-date checks must report WAIT_FOR_DATA.
    history = history.sort_values("Date", kind="mergesort")
    # Keep duplicate session rows visible so downstream completeness checks
    # cannot turn an ambiguous source into one apparently valid daily candle.
    for col in ("OpnPric", "HghPric", "LwPric", "ClsPric", "TtlTradgVol"):
        if col in history.columns:
            history[col] = pd.to_numeric(history[col], errors="coerce")
    return history.reset_index(drop=True), market_sessions

def _delivery_observations(symbol, series, sessions, asof):
    observations = []
    by_day = {}
    duplicate_dates = set()
    for raw_day, raw in sessions or []:
        day = _session_date(raw_day)
        if day is None or day > asof:
            continue
        if day in by_day or day in duplicate_dates:
            duplicate_dates.add(day)
            by_day.pop(day, None)
            continue
        by_day[day] = raw
    for day in sorted(by_day):
        raw = by_day[day]
        if raw is None or raw.empty:
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
    output_path: str | Path | None = None,
) -> pd.DataFrame:
    """Create non-gating quantity/price/base/supply observations for A/B names."""
    if candidates is None or candidates.empty:
        return pd.DataFrame()
    asof = _session_date(asof_date)
    if asof is None:
        raise ValueError(f"Invalid as-of date: {asof_date!r}")
    history_index, ordered_market_sessions = build_price_history_index(historical, asof)

    rows = []
    for _, candidate in candidates.drop_duplicates("TckrSymb", keep="first").iterrows():
        symbol = str(candidate.get("TckrSymb", "")).strip().upper()
        series = str(candidate.get("SctySrs", "EQ")).strip().upper() or "EQ"
        hist = candidate_price_history(history_index, candidate, asof)
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
            "HighDeliveryPriceResponseStatus": "WAIT_FOR_DATA",
            "SellingPressureObservationStatus": "WAIT_FOR_DATA",
            "DownDayCount20D": float("nan"), "UpDayCount20D": float("nan"),
            "DownDayVolumeAverage20D": float("nan"),
            "UpDayVolumeAverage20D": float("nan"),
            "DownVsUpVolumeRatio20D": float("nan"),
            "PivotStructureStatus": "WAIT_FOR_DATA",
            "ConfirmedPivotLowCount": float("nan"), "ConfirmedPivotHighCount": float("nan"),
            "LatestPivotLow": float("nan"), "PreviousPivotLow": float("nan"),
            "LatestPivotLowDate": "", "PreviousPivotLowDate": "",
            "ATR14": float("nan"), "PivotLowSeparationAbs": float("nan"),
            "PivotLowSeparationPct": float("nan"), "PivotLowSeparationATR": float("nan"),
            "PivotLowSeparationStatus": "WAIT_FOR_DATA",
            "ObservedEMA20": float("nan"), "ObservedEMA44": float("nan"),
            "ObservedEMA50": float("nan"), "ObservedEMA200": float("nan"),
            "ObservedEMA20DistancePct": float("nan"), "ObservedEMA44DistancePct": float("nan"),
            "ObservedEMA50DistancePct": float("nan"), "ObservedEMA200DistancePct": float("nan"),
            "ObservedEMA20Position": "WAIT_FOR_DATA", "ObservedEMA44Position": "WAIT_FOR_DATA",
            "ObservedEMA50Position": "WAIT_FOR_DATA", "ObservedEMA200Position": "WAIT_FOR_DATA",
            "ObservedEMA20Status": "WAIT_FOR_DATA", "ObservedEMA44Status": "WAIT_FOR_DATA",
            "ObservedEMA50Status": "WAIT_FOR_DATA", "ObservedEMA200Status": "WAIT_FOR_DATA",
            "TrendObservationStatus": "WAIT_FOR_DATA",
            "HigherLowStatus": "WAIT_FOR_DATA",
        }
        for window in RANGE_WINDOWS:
            prefix = f"PriceRange{window}D"
            row.update({
                f"{prefix}StartDate": "",
                f"{prefix}EndDate": "",
                f"{prefix}SessionCount": float("nan"),
                f"{prefix}AverageDailyRangePct": float("nan"),
                f"{prefix}LatestClosePositionPct": float("nan"),
            })
        if not hist.empty:
            hist_dates = hist["Date"].dt.date
            pivot_history_complete = (
                len(hist) == len(ordered_market_sessions)
                and hist_dates.nunique() == len(ordered_market_sessions)
                and set(hist_dates) == set(ordered_market_sessions)
            )
            if pivot_history_complete and "LwPric" in hist.columns and "HghPric" in hist.columns and hist[["LwPric", "HghPric"]].notna().all().all():
                row["PivotStructureStatus"] = "COMPLETE"
                row["ATR14"] = _atr14(hist)
                lows = hist["LwPric"].tolist()
                highs = hist["HghPric"].tolist()
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
                    separation = abs(low_pivots[-1][1] - value)
                    row["PivotLowSeparationAbs"] = separation
                    row["PivotLowSeparationPct"] = separation / value * 100.0 if value > 0 else float("nan")
                    row["PivotLowSeparationATR"] = separation / row["ATR14"] if pd.notna(row["ATR14"]) and row["ATR14"] > 0 else float("nan")
                    row["PivotLowSeparationStatus"] = "OBSERVATION_AVAILABLE" if pd.notna(row["PivotLowSeparationATR"]) else "WAIT_FOR_DATA"
                    row["HigherLowStatus"] = "HIGHER_LOW_OBSERVED" if low_pivots[-1][1] > value else "NO_HIGHER_LOW_OBSERVED"
                elif len(low_pivots) == 1:
                    row["HigherLowStatus"] = "WAIT_FOR_SECOND_CONFIRMED_PIVOT"
            for window in RANGE_WINDOWS:
                prefix = f"PriceRange{window}D"
                if len(hist) < window or "HghPric" not in hist.columns or "LwPric" not in hist.columns:
                    row[f"{prefix}Status"] = "WAIT_FOR_DATA"
                    for suffix in ("High", "Low", "WidthPct", "SessionsSinceLow", "SessionsSinceHigh", "ExactLowTouchCount", "ExactHighTouchCount", "StartDate", "EndDate", "SessionCount", "AverageDailyRangePct", "LatestClosePositionPct"):
                        row[f"{prefix}{suffix}"] = float("nan")
                    continue
                window_dates = ordered_market_sessions[-window:]
                part = hist[hist["Date"].dt.date.isin(window_dates)].copy()
                if (
                    len(window_dates) != window or len(part) != window
                    or part["Date"].dt.date.nunique() != window
                    or set(part["Date"].dt.date) != set(window_dates)
                    or not {"HghPric", "LwPric", "ClsPric"}.issubset(part.columns)
                    or part[["HghPric", "LwPric", "ClsPric"]].isna().any().any()
                    or not part[["HghPric", "LwPric", "ClsPric"]].apply(
                        lambda column: column.map(
                            lambda value: math.isfinite(float(value)) and float(value) > 0
                        )
                    ).all().all()
                    or (part["HghPric"] < part["LwPric"]).any()
                    or (part["ClsPric"] < part["LwPric"]).any()
                    or (part["ClsPric"] > part["HghPric"]).any()
                ):
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
                row[f"{prefix}StartDate"] = part.iloc[0]["Date"].date().isoformat()
                row[f"{prefix}EndDate"] = part.iloc[-1]["Date"].date().isoformat()
                row[f"{prefix}SessionCount"] = len(part)
                row[f"{prefix}AverageDailyRangePct"] = (
                    ((part["HghPric"] - part["LwPric"]) / part["ClsPric"]) * 100.0
                ).mean()
                latest_close = _num(part.iloc[-1]["ClsPric"])
                row[f"{prefix}LatestClosePositionPct"] = (
                    (latest_close - range_low) / (range_high - range_low) * 100.0
                    if range_high > range_low else float("nan")
                )

            row["PriceHistoryStatus"] = (
                "COMPLETE_20D" if row.get("PriceRange20DStatus") == "OBSERVATION_AVAILABLE"
                else "WAIT_FOR_DATA"
            )

            ema_statuses = []
            for period in (20, 44, 50, 200):
                obs = _ema_window_observation(hist, ordered_market_sessions, period)
                prefix = f"ObservedEMA{period}"
                row[f"{prefix}Status"] = obs["status"]
                ema_statuses.append(obs["status"])
                if obs["status"] == "COMPLETE":
                    row[prefix] = obs["value"]
                    row[f"{prefix}DistancePct"] = obs["distance_pct"]
                    row[f"{prefix}Position"] = obs["position"]
            if all(status == "COMPLETE" for status in ema_statuses):
                row["TrendObservationStatus"] = "COMPLETE"
            elif any(status == "COMPLETE" for status in ema_statuses):
                row["TrendObservationStatus"] = "PARTIAL_DATA"
            else:
                row["TrendObservationStatus"] = "WAIT_FOR_DATA"

            recent_dates = ordered_market_sessions[-20:]
            recent = hist[hist["Date"].dt.date.isin(recent_dates)].copy().sort_values("Date")
            if (
                len(recent_dates) == 20 and len(recent) == 20
                and recent["Date"].dt.date.nunique() == 20
                and set(recent["Date"].dt.date) == set(recent_dates)
                and recent["ClsPric"].notna().all()
            ):
                recent["CloseReturnPct"] = recent["ClsPric"].pct_change() * 100.0
            else:
                recent = pd.DataFrame()
            if "TtlTradgVol" in recent.columns:
                recent["TtlTradgVol"] = pd.to_numeric(recent["TtlTradgVol"], errors="coerce")
            if not recent.empty:
                down = recent[recent["CloseReturnPct"] < 0]
                up = recent[recent["CloseReturnPct"] > 0]
                row["DownDayCount20D"] = len(down)
                row["UpDayCount20D"] = len(up)
                volume_complete = (
                    "TtlTradgVol" in recent.columns
                    and recent["TtlTradgVol"].notna().all()
                    and (recent["TtlTradgVol"] >= 0).all()
                )
                if volume_complete:
                    down_avg = down["TtlTradgVol"].mean()
                    up_avg = up["TtlTradgVol"].mean()
                    row["DownDayVolumeAverage20D"] = down_avg
                    row["UpDayVolumeAverage20D"] = up_avg
                    row["DownVsUpVolumeRatio20D"] = (
                        down_avg / up_avg
                        if pd.notna(down_avg) and pd.notna(up_avg) and up_avg > 0
                        else float("nan")
                    )
                    row["SellingPressureObservationStatus"] = "OBSERVATIONS_AVAILABLE"
                else:
                    row["DownDayVolumeAverage20D"] = float("nan")
                    row["UpDayVolumeAverage20D"] = float("nan")
                    row["DownVsUpVolumeRatio20D"] = float("nan")
                    row["SellingPressureObservationStatus"] = "WAIT_FOR_DATA"

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
            if not high_delivery:
                row["HighDeliveryPriceResponseStatus"] = "NO_HIGH_DELIVERY_SESSION"
            elif abs_changes and ranges:
                row["HighDeliveryPriceResponseStatus"] = "OBSERVATIONS_AVAILABLE"
            elif abs_changes or ranges:
                row["HighDeliveryPriceResponseStatus"] = "PARTIAL_DATA"
            else:
                row["HighDeliveryPriceResponseStatus"] = "WAIT_FOR_DATA"
        else:
            row["DeliveryEvidenceStatus"] = "WAIT_FOR_DATA"
        if row["PriceHistoryStatus"] == "COMPLETE_20D" and row["DeliveryEvidenceStatus"] == "OBSERVATIONS_AVAILABLE":
            row["EvidenceStatus"] = "OBSERVATIONS_AVAILABLE"
        elif row["PriceHistoryStatus"] == "WAIT_FOR_DATA" and row["DeliveryEvidenceStatus"] == "WAIT_FOR_DATA":
            row["EvidenceStatus"] = "WAIT_FOR_DATA"
        else:
            row["EvidenceStatus"] = "PARTIAL_DATA"
        rows.append(row)

    report = pd.DataFrame(rows)
    target_path = Path(output_path) if output_path is not None else OUTPUT_DIR / f"v8_potential_accumulation_observations_{asof:%Y%m%d}.csv"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(target_path, index=False)
    return report
