"""Research-only Delivery A/B cohort forward-outcome backtest on cached NSE EOD data.

Uses the approved 30-calendar-day Delivery rules (A: at least five qualifying
trailing 5-valid-session averages >=60%; B: at least five daily observations
>=60%), includes the A OR B union, and treats RVOL as descriptive only.
The prior-20-session average traded-value liquidity condition remains >= INR
1.5 crore. Forward 5/10/20-session outcomes use exact official NSE sessions.
No network calls, no live scanner changes, no fundamental claims.
"""
from __future__ import annotations

from pathlib import Path
from functools import lru_cache
import math
import pandas as pd
import numpy as np

from rsi_retest_existing_cache import _read_price_cache, _read_delivery_cache
from nse_trading_calendar import is_trading_session

PRICE_DIR = Path("data/bhavcopy")
DELIVERY_DIR = Path("data/cache/delivery")
OUTPUT_DIR = Path("outputs/rvol_strategy_backtest")
LIQUIDITY_MIN_INR = 15_000_000.0
HORIZONS = (5, 10, 20)


@lru_cache(maxsize=512)
def _is_official_session(day_iso: str) -> bool:
    """Cache calendar lookups; the official calendar JSON is otherwise read per call."""
    return is_trading_session(day_iso)


def delivery_window_dates(delivery_dates, asof_date, max_calendar_days: int = 30) -> list[pd.Timestamp]:
    """Return distinct delivery report dates inside the inclusive 30-calendar-day window."""
    asof = pd.Timestamp(asof_date).normalize()
    start = asof - pd.Timedelta(days=max_calendar_days - 1)
    return sorted({
        pd.Timestamp(day).normalize()
        for day in delivery_dates
        if start <= pd.Timestamp(day).normalize() <= asof
        and _is_official_session(pd.Timestamp(day).date().isoformat())
    })


def official_market_session_dates(start_date, end_date) -> list[pd.Timestamp]:
    """Enumerate every official NSE equity session, including special sessions, in a date range."""
    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()
    if end < start:
        return []
    return [
        pd.Timestamp(day).normalize()
        for day in pd.date_range(start, end, freq="D")
        if _is_official_session(pd.Timestamp(day).date().isoformat())
    ]


def forward_session_dates(market_dates, signal_date, horizon: int) -> list[pd.Timestamp]:
    """Return exactly the next N distinct market sessions, or [] if the horizon is incomplete."""
    dates = sorted(pd.Timestamp(day).normalize() for day in market_dates)
    signal = pd.Timestamp(signal_date).normalize()
    try:
        position = dates.index(signal)
    except ValueError:
        return []
    future = dates[position + 1:position + 1 + int(horizon)]
    return future if len(future) == int(horizon) else []


def classify_delivery(values: list[float]) -> tuple[str, str]:
    """Apply approved A/B counts over valid distinct reports in the 30-day window."""
    if len(values) < 5 or any(not math.isfinite(float(v)) or not 0 <= float(v) <= 100 for v in values):
        return "WAIT_FOR_DATA", "WAIT_FOR_DATA"
    valid = [float(v) for v in values]
    qualifying_a_windows = sum(
        sum(valid[index - 4:index + 1]) / 5.0 >= 60.0
        for index in range(4, len(valid))
    )
    qualifying_b_days = sum(value >= 60.0 for value in valid)
    a = "PASS" if qualifying_a_windows >= 5 else "REJECT"
    b = "PASS" if qualifying_b_days >= 5 else "REJECT"
    return a, b


def _metric(values: pd.Series, prefix: str) -> dict:
    vals = pd.to_numeric(values, errors="coerce").dropna()
    if vals.empty:
        return {f"{prefix}Observations": 0, f"{prefix}WinRatePct": np.nan,
                f"{prefix}AverageReturnPct": np.nan, f"{prefix}MedianReturnPct": np.nan,
                f"{prefix}ProfitFactor": np.nan}
    gains = float(vals[vals > 0].sum())
    losses = float(-vals[vals < 0].sum())
    pf = gains / losses if losses > 0 else (np.inf if gains > 0 else np.nan)
    return {f"{prefix}Observations": int(len(vals)),
            f"{prefix}WinRatePct": round(float((vals > 0).mean() * 100), 2),
            f"{prefix}AverageReturnPct": round(float(vals.mean()), 3),
            f"{prefix}MedianReturnPct": round(float(vals.median()), 3),
            f"{prefix}ProfitFactor": round(float(pf), 3) if math.isfinite(pf) else pf}


def run_backtest(price_dir: Path = PRICE_DIR, delivery_dir: Path = DELIVERY_DIR,
                 output_dir: Path = OUTPUT_DIR) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    prices, price_issues = _read_price_cache(price_dir)
    delivery_by_date, delivery_issues = _read_delivery_cache(delivery_dir)

    price_files = list(price_dir.glob("bhavcopy_????????.csv")) if price_dir.exists() else []
    delivery_files = list(delivery_dir.glob("sec_bhavdata_full_????????.csv")) if delivery_dir.exists() else []
    coverage = {
        "PriceCacheFiles": len(price_files), "PriceDates": int(prices["DATE"].nunique()) if not prices.empty else 0,
        "PriceRows": int(len(prices)), "Symbols": int(prices["SYMBOL"].nunique()) if not prices.empty else 0,
        "EarliestPriceDate": str(prices["DATE"].min().date()) if not prices.empty else "",
        "LatestPriceDate": str(prices["DATE"].max().date()) if not prices.empty else "",
        "DeliveryCacheFiles": len(delivery_files), "DeliveryDates": len(delivery_by_date),
        "EarliestDeliveryDate": str(min(delivery_by_date).date()) if delivery_by_date else "",
        "LatestDeliveryDate": str(max(delivery_by_date).date()) if delivery_by_date else "",
        "PriceFileIssues": len(price_issues), "DeliveryFileIssues": len(delivery_issues),
        "NetworkCallsMade": False, "FundamentalsBacktested": False,
        "UniverseLimitation": "EQ series only; historical official Main Board/ETF classification is not present in this cache.",
        "SurvivorshipLimitation": "Current cache membership is not a point-in-time historical universe.",
        "CostsAndSlippage": "Not included; returns are close-to-close research measurements, not executable trade returns.",
    }
    pd.DataFrame([coverage]).to_csv(output_dir / "cache_coverage.csv", index=False)
    pd.DataFrame({"Issue": price_issues + delivery_issues}).to_csv(output_dir / "cache_file_issues.csv", index=False)
    if prices.empty or not delivery_by_date:
        pd.DataFrame([{"Status": "WAIT_FOR_DATA", "Reason": "Valid price and delivery cache files are both required; no network access is used."}]).to_csv(output_dir / "comparison.csv", index=False)
        pd.DataFrame().to_csv(output_dir / "signals.csv", index=False)
        pd.DataFrame([{"Stage": "backtest", "Rows": 0, "Status": "WAIT_FOR_DATA"}]).to_csv(output_dir / "rejection_counts.csv", index=False)
        print("[DELIVERY BACKTEST] WAIT_FOR_DATA: cached price or delivery history is missing.")
        return {"status": "WAIT_FOR_DATA", "price_rows": len(prices), "delivery_dates": len(delivery_by_date)}

    prices = prices.sort_values(["DATE", "SYMBOL"]).reset_index(drop=True)
    # Build the full official session calendar, not merely dates with downloaded
    # files. A missing whole-market Bhavcopy must not shift prior-20 or forward-N
    # horizons to the next available file.
    market_dates = official_market_session_dates(prices["DATE"].min(), prices["DATE"].max())
    date_to_pos = {d: i for i, d in enumerate(market_dates)}
    price_groups = {sym: frame.sort_values("DATE").reset_index(drop=True)
                    for sym, frame in prices.groupby("SYMBOL", sort=True)}
    delivery_dates = sorted(pd.Timestamp(x).normalize() for x in delivery_by_date)
    # Pre-index delivery rows and 30-day windows once. Re-filtering pandas
    # frames for every symbol/session would make the 200-day cache needlessly slow.
    delivery_lookup = {
        day: {
            str(symbol).strip().upper(): float(value)
            for symbol, value in zip(frame["SYMBOL"], frame["DELIV_PER"])
            if pd.notna(value) and math.isfinite(float(value)) and 0.0 <= float(value) <= 100.0
        }
        for day, frame in delivery_by_date.items()
    }
    delivery_windows = {
        day: delivery_window_dates(delivery_dates, day, max_calendar_days=30)
        for day in market_dates
    }
    records = []
    rejection = {"insufficient_price_history": 0, "insufficient_delivery_history": 0,
                 "delivery_a_and_b_reject": 0, "liquidity_below_1_5cr": 0,
                 "invalid_rvol": 0}

    for symbol, frame in price_groups.items():
        frame = frame.sort_values("DATE").reset_index(drop=True)
        date_values = pd.to_datetime(frame["DATE"]).dt.normalize().to_numpy()
        date_index = {
            pd.Timestamp(raw_date).normalize(): idx
            for idx, raw_date in enumerate(date_values)
        }
        volume_values = pd.to_numeric(frame["VOLUME"], errors="coerce").to_numpy(dtype=float)
        traded_values = pd.to_numeric(frame["TRADED_VALUE"], errors="coerce").to_numpy(dtype=float)
        close_values = pd.to_numeric(frame["CLOSE"], errors="coerce").to_numpy(dtype=float)
        high_values = pd.to_numeric(frame["HIGH"], errors="coerce").to_numpy(dtype=float)
        low_values = pd.to_numeric(frame["LOW"], errors="coerce").to_numpy(dtype=float)

        for row_idx, raw_date in enumerate(date_values):
            date = pd.Timestamp(raw_date).normalize()
            pos = date_to_pos.get(date, -1)
            if pos < 20:
                rejection["insufficient_price_history"] += 1
                continue
            prior_dates = market_dates[pos-20:pos]
            prior_indices = [date_index.get(day) for day in prior_dates]
            if any(idx is None for idx in prior_indices):
                rejection["insufficient_price_history"] += 1
                continue

            index_array = np.asarray(prior_indices, dtype=int)
            volumes = volume_values[index_array]
            values = traded_values[index_array]
            current_volume = volume_values[row_idx]
            current_close = close_values[row_idx]
            if (
                not np.isfinite(volumes).all()
                or not np.isfinite(values).all()
                or (volumes < 0).any()
                or (values < 0).any()
                or not math.isfinite(float(current_volume))
                or current_volume < 0
                or not math.isfinite(float(current_close))
                or current_close <= 0
            ):
                rejection["invalid_rvol"] += 1
                continue
            avg_volume = float(np.mean(volumes))
            avg_value = float(np.mean(values))
            if avg_volume <= 0:
                rejection["invalid_rvol"] += 1
                continue
            rvol = float(current_volume) / avg_volume

            eligible_delivery_dates = delivery_windows.get(date, [])
            dvalues = []
            candidate_delivery_dates = []
            for delivery_day in eligible_delivery_dates:
                value = delivery_lookup.get(delivery_day, {}).get(symbol)
                if value is None:
                    continue
                candidate_delivery_dates.append(delivery_day)
                dvalues.append(value)
            if len(dvalues) < 5:
                rejection["insufficient_delivery_history"] += 1
                continue
            cat_a, cat_b = classify_delivery(dvalues)
            qualifying_a_windows = sum(
                sum(float(v) for v in dvalues[index - 4:index + 1]) / 5.0 >= 60.0
                for index in range(4, len(dvalues))
            )
            qualifying_b_days = sum(float(v) >= 60.0 for v in dvalues)
            if cat_a != "PASS" and cat_b != "PASS":
                rejection["delivery_a_and_b_reject"] += 1
                continue
            if avg_value < LIQUIDITY_MIN_INR:
                rejection["liquidity_below_1_5cr"] += 1
                continue

            delivery_cohort = (
                "A_AND_B" if cat_a == "PASS" and cat_b == "PASS"
                else "A_ONLY" if cat_a == "PASS" else "B_ONLY"
            )
            rec = {
                "Date": date.date().isoformat(), "Symbol": symbol, "Close": current_close,
                "CurrentVolume": float(current_volume), "AvgVolume20D": avg_volume, "RVOL": rvol,
                "AvgTradedValue20D_INR": avg_value, "Delivery30D_AveragePct": sum(dvalues) / len(dvalues),
                "Delivery30D_MinPct": min(dvalues), "DeliveryCategoryA": cat_a, "DeliveryCategoryB": cat_b,
                "DeliveryValidReportCount": len(dvalues),
                "DeliveryQualifyingAWindows": qualifying_a_windows,
                "DeliveryQualifyingBDays": qualifying_b_days,
                "DeliveryCohort": delivery_cohort,
                "DeliverySessionDates": "|".join(d.strftime("%Y-%m-%d") for d in candidate_delivery_dates),
                "RVOLRole": "DESCRIPTIVE_ONLY_NO_HARD_GATE",
                "UniverseStatus": "EQ_SERIES_ONLY_HISTORICAL_MAINBOARD_NOT_VERIFIED",
            }
            for horizon in HORIZONS:
                expected_dates = forward_session_dates(market_dates, date, horizon)
                future_indices = [date_index.get(day) for day in expected_dates] if expected_dates else []
                complete = (
                    len(expected_dates) == horizon
                    and len(future_indices) == horizon
                    and all(idx is not None for idx in future_indices)
                )
                if complete:
                    future_index_array = np.asarray(future_indices, dtype=int)
                    future_closes = close_values[future_index_array]
                    complete = np.isfinite(future_closes).all() and (future_closes > 0).all()
                else:
                    future_index_array = np.asarray([], dtype=int)
                    future_closes = np.asarray([], dtype=float)

                rec[f"ForwardReturn{horizon}D_Pct"] = (
                    (float(future_closes[-1]) / current_close - 1) * 100 if complete else np.nan
                )
                future_highs = high_values[future_index_array] if complete else np.asarray([], dtype=float)
                future_lows = low_values[future_index_array] if complete else np.asarray([], dtype=float)
                valid_future_ohlc = (
                    complete
                    and np.isfinite(future_highs).all()
                    and np.isfinite(future_lows).all()
                    and (future_highs > 0).all()
                    and (future_lows > 0).all()
                    and (future_lows <= future_highs).all()
                )
                rec[f"MaxFavorable{horizon}D_Pct"] = (
                    (float(np.max(future_highs)) / current_close - 1) * 100
                    if valid_future_ohlc else np.nan
                )
                rec[f"MaxAdverse{horizon}D_Pct"] = (
                    (float(np.min(future_lows) / current_close - 1) * 100)
                    if valid_future_ohlc else np.nan
                )
            records.append(rec)

    signals = pd.DataFrame(records)
    if signals.empty:
        signals = pd.DataFrame(columns=["Date", "Symbol", "Close", "RVOL", "DeliveryCategoryA", "DeliveryCategoryB", "DeliveryCohort", *[f"ForwardReturn{h}D_Pct" for h in HORIZONS], *[f"MaxFavorable{h}D_Pct" for h in HORIZONS], *[f"MaxAdverse{h}D_Pct" for h in HORIZONS]])
    signals.to_csv(output_dir / "signals.csv", index=False)
    pd.DataFrame([{"Stage": k, "Rows": v} for k, v in rejection.items()]).to_csv(output_dir / "rejection_counts.csv", index=False)

    comparison = []
    for cohort in ("A_OR_B", "A_ONLY", "A_AND_B", "B_ONLY"):
        if signals.empty:
            group = signals.copy()
        elif cohort == "A_OR_B":
            group = signals.copy()
        else:
            group = signals[signals["DeliveryCohort"].eq(cohort)].copy()
        row = {
            "DeliveryCohort": cohort, "SignalCount": int(len(group)),
            "RVOLRole": "DESCRIPTIVE_ONLY_NO_HARD_GATE",
            "LiquidityGate": "20 prior official sessions average traded value >= INR 1.5 crore",
            "DeliveryGate": "30 calendar days; A = at least 5 trailing 5-valid-session averages >=60%; B = at least 5 daily reports >=60%; A OR B",
            "FundamentalStatus": "NOT_BACKTESTED_NO_POINT_IN_TIME_FUNDAMENTAL_HISTORY",
        }
        for h in HORIZONS:
            row.update(_metric(group[f"ForwardReturn{h}D_Pct"], f"Return{h}D"))
            row[f"AvgMFE{h}D_Pct"] = round(float(pd.to_numeric(group[f"MaxFavorable{h}D_Pct"], errors="coerce").mean()), 3) if len(group) else np.nan
            row[f"AvgMAE{h}D_Pct"] = round(float(pd.to_numeric(group[f"MaxAdverse{h}D_Pct"], errors="coerce").mean()), 3) if len(group) else np.nan
        comparison.append(row)
    comp = pd.DataFrame(comparison)
    comp["BacktestStatus"] = "RESEARCH_ONLY_NOT_PRODUCTION_VALIDATED"
    comp["Caveat"] = "No transaction costs/slippage or portfolio simulation; daily signals can repeat and overlap, so observations are not independent executed trades. EQ-only and current cache survivorship; historical official Main Board classification and point-in-time fundamentals unavailable. Forward outcomes require every symbol row on each of the next official market dates; incomplete horizons are excluded."
    comp.to_csv(output_dir / "comparison.csv", index=False)
    print(f"[DELIVERY BACKTEST] Cache dates={len(market_dates)}, symbols={len(price_groups)}, A-or-B signal rows={len(signals)}")
    print(f"[DELIVERY BACKTEST] Comparison: {output_dir / 'comparison.csv'}; signals: {output_dir / 'signals.csv'}")
    print("[DELIVERY BACKTEST] Research only; RVOL descriptive, no scanner filter or Master Spec was changed.")
    return {"status": "OK", "price_dates": len(market_dates), "symbols": len(price_groups), "signals": len(signals)}



if __name__ == "__main__":
    run_backtest()
