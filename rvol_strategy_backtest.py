"""Research-only comparison of three RVOL gates on cached NSE EOD data.

Strategies are compared on the same historical universe and gates:
5-session Delivery Category A (average >=60%) + prior-20-session liquidity
(average traded value >= INR 1.5 crore), then:
A) RVOL > 1.5; B) RVOL > 1.2; C) no hard RVOL threshold.
Category B (all five Delivery sessions >=60%) is reported as a stricter subgroup.
No network calls, no live scanner changes, no fundamental claims.
"""
from __future__ import annotations

from pathlib import Path
import math
import pandas as pd
import numpy as np

from rsi_retest_existing_cache import _read_price_cache, _read_delivery_cache

PRICE_DIR = Path("data/bhavcopy")
DELIVERY_DIR = Path("data/cache/delivery")
OUTPUT_DIR = Path("outputs/rvol_strategy_backtest")
LIQUIDITY_MIN_INR = 15_000_000.0
HORIZONS = (5, 10, 20)


def delivery_window_dates(delivery_dates, asof_date, max_calendar_days: int = 30) -> list[pd.Timestamp]:
    """Return distinct delivery report dates inside the inclusive 30-calendar-day window."""
    asof = pd.Timestamp(asof_date).normalize()
    start = asof - pd.Timedelta(days=max_calendar_days - 1)
    return sorted({
        pd.Timestamp(day).normalize()
        for day in delivery_dates
        if start <= pd.Timestamp(day).normalize() <= asof
    })


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
    """Classify all valid candidate reports in the 30-day window; at least five are required."""
    if len(values) < 5 or any(not math.isfinite(float(v)) or not 0 <= float(v) <= 100 for v in values):
        return "WAIT_FOR_DATA", "WAIT_FOR_DATA"
    a = "PASS" if sum(values) / len(values) >= 60.0 else "REJECT"
    b = "PASS" if all(float(v) >= 60.0 for v in values) else "REJECT"
    return a, b


def strategy_membership(rvol: float) -> tuple[bool, bool, bool]:
    """Return membership in strict >1.5, relaxed >1.2, and no-hard-gate strategies."""
    if not math.isfinite(float(rvol)):
        return False, False, False
    value = float(rvol)
    return value > 1.5, value > 1.2, True


def _metric(values: pd.Series, prefix: str) -> dict:
    vals = pd.to_numeric(values, errors="coerce").dropna()
    if vals.empty:
        return {f"{prefix}Trades": 0, f"{prefix}WinRatePct": np.nan,
                f"{prefix}AverageReturnPct": np.nan, f"{prefix}MedianReturnPct": np.nan,
                f"{prefix}ProfitFactor": np.nan}
    gains = float(vals[vals > 0].sum())
    losses = float(-vals[vals < 0].sum())
    pf = gains / losses if losses > 0 else (np.inf if gains > 0 else np.nan)
    return {f"{prefix}Trades": int(len(vals)),
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
        print("[RVOL BACKTEST] WAIT_FOR_DATA: cached price or delivery history is missing.")
        return {"status": "WAIT_FOR_DATA", "price_rows": len(prices), "delivery_dates": len(delivery_by_date)}

    prices = prices.sort_values(["DATE", "SYMBOL"]).reset_index(drop=True)
    market_dates = sorted(pd.Timestamp(x).normalize() for x in prices["DATE"].dropna().unique())
    date_to_pos = {d: i for i, d in enumerate(market_dates)}
    price_groups = {sym: frame.sort_values("DATE").reset_index(drop=True)
                    for sym, frame in prices.groupby("SYMBOL", sort=True)}
    delivery_dates = sorted(pd.Timestamp(x).normalize() for x in delivery_by_date)
    records = []
    rejection = {"insufficient_price_history": 0, "insufficient_delivery_history": 0,
                 "delivery_category_a_reject": 0, "liquidity_below_1_5cr": 0,
                 "invalid_rvol": 0}

    for symbol, frame in price_groups.items():
        by_date = {pd.Timestamp(row.DATE).normalize(): row for row in frame.itertuples(index=False)}
        for date, current in by_date.items():
            pos = date_to_pos.get(date, -1)
            if pos < 20:
                rejection["insufficient_price_history"] += 1
                continue
            prior_dates = market_dates[pos-20:pos]
            prior_rows = [by_date.get(d) for d in prior_dates]
            if any(row is None for row in prior_rows):
                rejection["insufficient_price_history"] += 1
                continue
            volumes = pd.to_numeric(pd.Series([r.VOLUME for r in prior_rows]), errors="coerce")
            values = pd.to_numeric(pd.Series([r.TRADED_VALUE for r in prior_rows]), errors="coerce")
            current_volume = pd.to_numeric(pd.Series([current.VOLUME]), errors="coerce").iloc[0]
            if volumes.isna().any() or values.isna().any() or (volumes < 0).any() or (values < 0).any() or pd.isna(current_volume):
                rejection["invalid_rvol"] += 1
                continue
            avg_volume = float(volumes.mean())
            avg_value = float(values.mean())
            if avg_volume <= 0:
                rejection["invalid_rvol"] += 1
                continue
            rvol = float(current_volume) / avg_volume

            eligible_delivery_dates = delivery_window_dates(delivery_dates, date, max_calendar_days=30)
            dvalues = []
            candidate_delivery_dates = []
            for d in eligible_delivery_dates:
                df = delivery_by_date[d]
                hit = df.loc[df["SYMBOL"].eq(symbol), "DELIV_PER"]
                if hit.empty or pd.isna(hit.iloc[-1]):
                    continue
                value = float(hit.iloc[-1])
                if not math.isfinite(value) or not 0.0 <= value <= 100.0:
                    continue
                candidate_delivery_dates.append(d)
                dvalues.append(value)
            if len(dvalues) < 5:
                rejection["insufficient_delivery_history"] += 1
                continue
            cat_a, cat_b = classify_delivery(dvalues)
            if cat_a != "PASS":
                rejection["delivery_category_a_reject"] += 1
                continue
            if avg_value < LIQUIDITY_MIN_INR:
                rejection["liquidity_below_1_5cr"] += 1
                continue

            strict, relaxed, no_gate = strategy_membership(rvol)
            rec = {
                "Date": date.date().isoformat(), "Symbol": symbol, "Close": float(current.CLOSE),
                "CurrentVolume": float(current_volume), "AvgVolume20D": avg_volume, "RVOL": rvol,
                "AvgTradedValue20D_INR": avg_value, "Delivery5D_AveragePct": sum(dvalues)/5,
                "Delivery5D_MinPct": min(dvalues), "DeliveryCategoryA": cat_a, "DeliveryCategoryB": cat_b,
                "DeliveryValidReportCount": len(dvalues),
                "DeliverySessionDates": "|".join(d.strftime("%Y-%m-%d") for d in candidate_delivery_dates),
                "Strategy_A_RVOL_GT_1_5": strict, "Strategy_B_RVOL_GT_1_2": relaxed,
                "Strategy_C_No_RVOL_Hard_Gate": no_gate,
                "UniverseStatus": "EQ_SERIES_ONLY_HISTORICAL_MAINBOARD_NOT_VERIFIED",
            }
            for horizon in HORIZONS:
                expected_dates = forward_session_dates(market_dates, date, horizon)
                future = frame[frame["DATE"].isin(expected_dates)].sort_values("DATE") if expected_dates else frame.iloc[0:0]
                complete = (
                    len(expected_dates) == horizon
                    and len(future) == horizon
                    and list(pd.to_datetime(future["DATE"]).dt.normalize()) == expected_dates
                    and future["CLOSE"].notna().all()
                    and future["CLOSE"].gt(0).all()
                )
                rec[f"ForwardReturn{horizon}D_Pct"] = (
                    (float(future.iloc[-1]["CLOSE"]) / float(current.CLOSE) - 1) * 100 if complete else np.nan
                )
                rec[f"MaxFavorable{horizon}D_Pct"] = (
                    (float(future["HIGH"].max()) / float(current.CLOSE) - 1) * 100
                    if complete and future["HIGH"].notna().all() and future["HIGH"].gt(0).all() else np.nan
                )
                rec[f"MaxAdverse{horizon}D_Pct"] = (
                    (float(future["LOW"].min()) / float(current.CLOSE) - 1) * 100
                    if complete and future["LOW"].notna().all() and future["LOW"].gt(0).all() else np.nan
                )
            records.append(rec)

    signals = pd.DataFrame(records)
    if signals.empty:
        signals = pd.DataFrame(columns=["Date", "Symbol", "Close", "RVOL", "DeliveryCategoryA", "DeliveryCategoryB", *[f"ForwardReturn{h}D_Pct" for h in HORIZONS], *[f"MaxFavorable{h}D_Pct" for h in HORIZONS], *[f"MaxAdverse{h}D_Pct" for h in HORIZONS], "Strategy_A_RVOL_GT_1_5", "Strategy_B_RVOL_GT_1_2", "Strategy_C_No_RVOL_Hard_Gate"])
    signals.to_csv(output_dir / "signals.csv", index=False)
    pd.DataFrame([{"Stage": k, "Rows": v} for k, v in rejection.items()]).to_csv(output_dir / "rejection_counts.csv", index=False)

    comparison = []
    strategy_map = {
        "A_RVOL_GT_1_5": "Strategy_A_RVOL_GT_1_5",
        "B_RVOL_GT_1_2": "Strategy_B_RVOL_GT_1_2",
        "C_NO_RVOL_HARD_GATE": "Strategy_C_No_RVOL_Hard_Gate",
    }
    for label, flag in strategy_map.items():
        subset = signals[signals[flag].fillna(False)].copy() if not signals.empty else signals.copy()
        for category in ("A", "B"):
            group = subset if category == "A" else subset[subset["DeliveryCategoryB"].eq("PASS")]
            row = {"Strategy": label, "DeliveryCohort": category, "SignalCount": int(len(group)),
                   "RVOLThreshold": {"A_RVOL_GT_1_5": ">1.5", "B_RVOL_GT_1_2": ">1.2", "C_NO_RVOL_HARD_GATE": "none"}[label],
                   "LiquidityGate": "20 prior sessions average traded value >= INR 1.5 crore",
                   "DeliveryGate": "all valid candidate reports in prior 30 calendar days; minimum 5; average >=60%" if category == "A" else "all valid candidate reports in prior 30 calendar days; minimum 5; each >=60%",
                   "FundamentalStatus": "NOT_BACKTESTED_NO_POINT_IN_TIME_FUNDAMENTAL_HISTORY"}
            for h in HORIZONS:
                row.update(_metric(group[f"ForwardReturn{h}D_Pct"], f"Return{h}D"))
                row[f"AvgMFE{h}D_Pct"] = round(float(pd.to_numeric(group[f"MaxFavorable{h}D_Pct"], errors="coerce").mean()), 3) if len(group) else np.nan
                row[f"AvgMAE{h}D_Pct"] = round(float(pd.to_numeric(group[f"MaxAdverse{h}D_Pct"], errors="coerce").mean()), 3) if len(group) else np.nan
            comparison.append(row)
    comp = pd.DataFrame(comparison)
    comp["BacktestStatus"] = "RESEARCH_ONLY_NOT_PRODUCTION_VALIDATED"
    comp["Caveat"] = "No transaction costs/slippage; EQ-only and current cache survivorship; historical official Main Board classification and point-in-time fundamentals unavailable. Forward outcomes require every symbol row on each of the next official market dates; incomplete horizons are excluded."
    comp.to_csv(output_dir / "comparison.csv", index=False)
    print(f"[RVOL BACKTEST] Cache dates={len(market_dates)}, symbols={len(price_groups)}, qualified signal rows={len(signals)}")
    print(f"[RVOL BACKTEST] Comparison: {output_dir / 'comparison.csv'}; signals: {output_dir / 'signals.csv'}")
    print("[RVOL BACKTEST] Research only; no scanner filter or Master Spec was changed.")
    return {"status": "OK", "price_dates": len(market_dates), "symbols": len(price_groups), "signals": len(signals)}


if __name__ == "__main__":
    run_backtest()
