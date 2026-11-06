"""Independent potential-bottom and confirmed-reversal diagnostics.

This module is informational only. It does not modify the V8 candidate gates,
ranking, watchlist, risk controls, or place orders.
"""
from __future__ import annotations

from pathlib import Path
import math
import pandas as pd

OUTPUT_DIR = Path("outputs")
REPORT_COLUMNS = [
    "TckrSymb", "AsOfDate", "CurrentClose", "ATR14",
    "Support20DLow", "Support50DLow", "Support100DLow", "Support200DLow",
    "NearestSupport", "SupportSource", "SupportDistancePct", "NearSupportStatus",
    "ConfirmedPivotLow", "PreviousConfirmedPivotLow", "PivotLowDate",
    "HigherLowStatus", "DoubleBottomStatus", "DoubleBottomTolerance",
    "BullishCandleStatus", "SellingPressureStatus", "VolumeConfirmationStatus",
    "BreakoutConfirmationStatus", "EMA44ConfirmationStatus",
    "BottomCategory", "BottomStatus", "BottomReason",
]


def _number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else float("nan")
    except (TypeError, ValueError):
        return float("nan")


def _atr(frame: pd.DataFrame, period: int = 14) -> float:
    if len(frame) < period + 1:
        return float("nan")
    high = pd.to_numeric(frame["HghPric"], errors="coerce")
    low = pd.to_numeric(frame["LwPric"], errors="coerce")
    close = pd.to_numeric(frame["ClsPric"], errors="coerce")
    previous = close.shift(1)
    true_range = pd.concat(
        [(high - low), (high - previous).abs(), (low - previous).abs()],
        axis=1,
    ).max(axis=1)
    value = true_range.tail(period).mean()
    return _number(value)


def _confirmed_pivots(frame: pd.DataFrame, left: int = 3, right: int = 3):
    """Return pivot lows only after all right-side confirmation candles exist."""
    lows = pd.to_numeric(frame["LwPric"], errors="coerce").tolist()
    pivots = []
    for index in range(left, len(lows) - right):
        value = _number(lows[index])
        window = [_number(x) for x in lows[index-left:index+right+1]]
        if not math.isfinite(value) or any(not math.isfinite(x) for x in window):
            continue
        left_values = window[:left]
        right_values = window[left+1:]
        if value <= min(window) and value < max(left_values) and value < max(right_values):
            pivots.append((index, value))
    return pivots


def analyze_bottoms(candidates: pd.DataFrame, history_frames) -> pd.DataFrame:
    """Build Category A (potential) and Category B (confirmed) bottom diagnostics."""
    if candidates is None:
        candidates = pd.DataFrame()
    frames = []
    for frame in history_frames or []:
        if frame is not None and not frame.empty:
            frames.append(frame.copy())
    if frames:
        history = pd.concat(frames, ignore_index=True)
        history["TckrSymb"] = history["TckrSymb"].astype(str).str.upper()
        history["Date"] = pd.to_datetime(history["Date"], errors="coerce")
        history = history.dropna(subset=["TckrSymb", "Date"])
        history = history.sort_values(["TckrSymb", "Date"]).drop_duplicates(
            ["TckrSymb", "Date"], keep="last"
        )
    else:
        history = pd.DataFrame()

    rows = []
    for _, candidate in candidates.iterrows():
        symbol = str(candidate.get("TckrSymb", "")).upper()
        stock = (
            history[history["TckrSymb"].eq(symbol)].sort_values("Date").reset_index(drop=True)
            if not history.empty else pd.DataFrame()
        )
        close = _number(candidate.get("ClsPric"))
        if pd.isna(close) and not stock.empty:
            close = _number(stock.iloc[-1].get("ClsPric"))

        row = {column: float("nan") for column in REPORT_COLUMNS}
        row.update({
            "TckrSymb": symbol,
            "AsOfDate": str(stock.iloc[-1]["Date"].date()) if not stock.empty else "",
            "CurrentClose": close,
            "SupportSource": "WAIT_FOR_DATA",
            "NearSupportStatus": "WAIT_FOR_DATA",
            "HigherLowStatus": "WAIT_FOR_DATA",
            "DoubleBottomStatus": "WAIT_FOR_DATA",
            "BullishCandleStatus": "WAIT_FOR_DATA",
            "SellingPressureStatus": "WAIT_FOR_DATA",
            "VolumeConfirmationStatus": "WAIT_FOR_DATA",
            "BreakoutConfirmationStatus": "WAIT_FOR_DATA",
            "EMA44ConfirmationStatus": "WAIT_FOR_DATA",
            "BottomCategory": "NONE",
            "BottomStatus": "WAIT_FOR_DATA",
            "BottomReason": "Insufficient valid EOD history",
        })
        if stock.empty or len(stock) < 21 or pd.isna(close) or close <= 0:
            rows.append(row)
            continue

        for col in ["OpnPric", "HghPric", "LwPric", "ClsPric", "TtlTradgVol"]:
            if col in stock.columns:
                stock[col] = pd.to_numeric(stock[col], errors="coerce")
        stock = stock.dropna(subset=["HghPric", "LwPric", "ClsPric"]).reset_index(drop=True)
        if len(stock) < 21:
            rows.append(row)
            continue

        atr = _atr(stock)
        row["ATR14"] = atr
        support_levels = []
        for period in (20, 50, 100, 200):
            field = f"Support{period}DLow"
            if len(stock) >= period:
                value = float(stock.tail(period)["LwPric"].min())
                row[field] = value
                if value <= close:
                    support_levels.append((value, f"{period}D_LOW"))
        if support_levels:
            support, source = max(support_levels, key=lambda item: item[0])
            row["NearestSupport"] = support
            row["SupportSource"] = source
            distance = (close - support) / close * 100
            row["SupportDistancePct"] = distance
            near_support = distance <= 3.0 or (
                pd.notna(atr) and atr > 0 and close - support <= 1.5 * atr
            )
            row["NearSupportStatus"] = "NEAR_SUPPORT" if near_support else "NOT_NEAR_SUPPORT"
        else:
            near_support = False
            row["NearSupportStatus"] = "WAIT_FOR_DATA"

        pivots = _confirmed_pivots(stock, 3, 3)
        latest_pivot = pivots[-1] if pivots else None
        previous_pivot = pivots[-2] if len(pivots) >= 2 else None
        if latest_pivot:
            row["ConfirmedPivotLow"] = latest_pivot[1]
            row["PivotLowDate"] = str(stock.iloc[latest_pivot[0]]["Date"].date())
        if previous_pivot:
            row["PreviousConfirmedPivotLow"] = previous_pivot[1]

        higher_low = bool(
            latest_pivot and previous_pivot and latest_pivot[1] > previous_pivot[1]
        )
        row["HigherLowStatus"] = (
            "PASS_HIGHER_LOW" if higher_low else
            "FAIL_NOT_HIGHER_LOW" if latest_pivot and previous_pivot else
            "WAIT_FOR_DATA"
        )

        double_bottom = False
        tolerance = 0.75 * atr if pd.notna(atr) and atr > 0 else float("nan")
        row["DoubleBottomTolerance"] = tolerance
        if latest_pivot and previous_pivot and pd.notna(tolerance):
            double_bottom = abs(latest_pivot[1] - previous_pivot[1]) <= tolerance
            row["DoubleBottomStatus"] = "PASS_DOUBLE_BOTTOM" if double_bottom else "NO_DOUBLE_BOTTOM"
        else:
            row["DoubleBottomStatus"] = "WAIT_FOR_DATA"

        today = stock.iloc[-1]
        open_price = _number(today.get("OpnPric"))
        high_price = _number(today.get("HghPric"))
        low_price = _number(today.get("LwPric"))
        bullish = (
            pd.notna(open_price) and pd.notna(high_price) and pd.notna(low_price)
            and close > open_price and high_price > low_price
            and (close - low_price) / (high_price - low_price) >= 0.60
        )
        row["BullishCandleStatus"] = "PASS_BULLISH_CANDLE" if bullish else "NO_BULLISH_CANDLE"

        volume = _number(today.get("TtlTradgVol"))
        previous_volumes = pd.to_numeric(stock.iloc[:-1].tail(20)["TtlTradgVol"], errors="coerce")
        average_volume = previous_volumes.mean() if len(previous_volumes.dropna()) >= 15 else float("nan")
        if pd.notna(volume) and pd.notna(average_volume) and average_volume > 0:
            row["VolumeConfirmationStatus"] = (
                "PASS_VOLUME_GE_1_2X_AVG20" if volume >= 1.2 * average_volume else "NO_VOLUME_CONFIRMATION"
            )
            row["SellingPressureStatus"] = (
                "SELLING_PRESSURE_DECLINING"
                if len(stock) >= 11 and stock.iloc[-5:]["TtlTradgVol"].mean() < stock.iloc[-10:-5]["TtlTradgVol"].mean()
                else "SELLING_PRESSURE_NOT_CONFIRMED"
            )
        else:
            row["VolumeConfirmationStatus"] = "WAIT_FOR_DATA"
            row["SellingPressureStatus"] = "WAIT_FOR_DATA"

        if latest_pivot:
            post_pivot = stock.iloc[latest_pivot[0]+1:-1]
            prior_swing_high = _number(post_pivot["HghPric"].max()) if not post_pivot.empty else float("nan")
            row["BreakoutConfirmationStatus"] = (
                "PASS_CLOSE_ABOVE_POST_PIVOT_SWING_HIGH"
                if pd.notna(prior_swing_high) and close > prior_swing_high
                else "NO_BREAKOUT_CONFIRMATION" if pd.notna(prior_swing_high)
                else "WAIT_FOR_DATA"
            )
        else:
            row["BreakoutConfirmationStatus"] = "WAIT_FOR_DATA"

        ema44 = _number(candidate.get("EMA44"))
        row["EMA44ConfirmationStatus"] = (
            "PASS_CLOSE_ABOVE_EMA44" if pd.notna(ema44) and close > ema44
            else "FAIL_CLOSE_NOT_ABOVE_EMA44" if pd.notna(ema44)
            else "WAIT_FOR_DATA"
        )

        potential_evidence = (
            bullish
            or row["SellingPressureStatus"] == "SELLING_PRESSURE_DECLINING"
            or bool(latest_pivot)
            or double_bottom
        )
        if near_support and potential_evidence:
            row["BottomCategory"] = "A_POTENTIAL_BOTTOM"
            row["BottomStatus"] = "BOTTOM_FORMING"
            row["BottomReason"] = "Price is near a verified lookback support and at least one early stabilization signal exists; reversal is not confirmed."
        else:
            row["BottomCategory"] = "NONE"
            row["BottomStatus"] = "NO_POTENTIAL_BOTTOM_SETUP"
            row["BottomReason"] = "Support proximity plus early stabilization evidence is not established."

        confirmed = (
            higher_low
            and bullish
            and row["BreakoutConfirmationStatus"] == "PASS_CLOSE_ABOVE_POST_PIVOT_SWING_HIGH"
            and row["VolumeConfirmationStatus"] == "PASS_VOLUME_GE_1_2X_AVG20"
            and row["EMA44ConfirmationStatus"] == "PASS_CLOSE_ABOVE_EMA44"
        )
        if confirmed:
            row["BottomCategory"] = "B_CONFIRMED_BOTTOM_REVERSAL"
            row["BottomStatus"] = "REVERSAL_CONFIRMED"
            row["BottomReason"] = "Confirmed higher pivot low, bullish candle, close above post-pivot swing high, >=1.2x prior 20-session average volume, and close above EMA44."
        elif row["BottomCategory"] == "A_POTENTIAL_BOTTOM":
            row["BottomReason"] += " 3-left/3-right pivots require all three right-side sessions; this is not a BUY signal."
        rows.append(row)

    return pd.DataFrame(rows, columns=REPORT_COLUMNS)


def write_bottom_detection_report(candidates: pd.DataFrame, history_frames, asof_date) -> pd.DataFrame:
    report = analyze_bottoms(candidates, history_frames)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = pd.Timestamp(asof_date).strftime("%Y%m%d")
    report.to_csv(OUTPUT_DIR / f"v8_bottom_detection_{stamp}.csv", index=False)
    summary = report["BottomCategory"].value_counts().to_dict() if not report.empty else {}
    print(f"[BOTTOM] Independent bottom report written: {len(report)} symbols; categories={summary}")
    return report
