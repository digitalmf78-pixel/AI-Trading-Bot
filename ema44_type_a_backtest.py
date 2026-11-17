"""Research-only Type A EMA44 pullback backtest on restored NSE cache.

No network calls, no cache writes, no production scanner changes. Uses the
approved Delivery A OR B and INR 1.5cr liquidity eligibility sequence, then
mirrors the EMA44-only Type A signal conditions. Entries are next-session
open (not signal-day close). Returns are reported net of explicitly stated,
configurable round-trip cost assumptions. Structural stop/target and 2R are
not fabricated; those require the live V8 structural-level engine.
"""
from __future__ import annotations

from pathlib import Path
import math
import os
import pandas as pd
import numpy as np

from rsi_retest_existing_cache import _read_price_cache, _norm_columns
from delivery_filter import validate_delivery_report_date
from rvol_strategy_backtest import (
    classify_delivery, delivery_window_dates, official_market_session_dates,
    forward_session_dates,
)

PRICE_DIR = Path("data/bhavcopy")
DELIVERY_DIR = Path("data/cache/delivery")
OUTPUT_DIR = Path("outputs/ema44_type_a_backtest")
LIQUIDITY_MIN_INR = 15_000_000.0
HORIZONS = (5, 10, 20)
ROUND_TRIP_COST_BPS = float(os.getenv("EMA44_BT_ROUND_TRIP_COST_BPS", "30"))
ENTRY_SLIPPAGE_BPS = float(os.getenv("EMA44_BT_ENTRY_SLIPPAGE_BPS", "10"))
EXIT_SLIPPAGE_BPS = float(os.getenv("EMA44_BT_EXIT_SLIPPAGE_BPS", "10"))
MIN_WARMUP_BARS = 44


def _summary(values: pd.Series, prefix: str) -> dict:
    vals = pd.to_numeric(values, errors="coerce").dropna()
    gains = float(vals[vals > 0].sum())
    losses = float(-vals[vals < 0].sum())
    pf = gains / losses if losses > 0 else (float("inf") if gains > 0 else np.nan)
    return {
        f"{prefix}Observations": int(len(vals)),
        f"{prefix}WinRatePct": round(float((vals > 0).mean() * 100), 2) if len(vals) else np.nan,
        f"{prefix}AverageNetReturnPct": round(float(vals.mean()), 3) if len(vals) else np.nan,
        f"{prefix}MedianNetReturnPct": round(float(vals.median()), 3) if len(vals) else np.nan,
        f"{prefix}ProfitFactor": round(float(pf), 3) if math.isfinite(pf) else pf,
    }



def _read_delivery_cache_strict(delivery_dir: Path) -> tuple[dict[pd.Timestamp, pd.DataFrame], list[str]]:
    """Read cached Delivery reports only after validating filename and internal DATE1."""
    by_date: dict[pd.Timestamp, pd.DataFrame] = {}
    rejected: list[str] = []
    files = sorted(delivery_dir.glob("sec_bhavdata_full_????????.csv")) if delivery_dir.exists() else []
    for path in files:
        import re
        match = re.fullmatch(r"sec_bhavdata_full_(\\d{8})\\.csv", path.name)
        if not match:
            continue
        report_date = pd.to_datetime(match.group(1), format="%d%m%Y", errors="coerce")
        if pd.isna(report_date):
            rejected.append(f"{path.name}: invalid filename date")
            continue
        try:
            frame = _norm_columns(pd.read_csv(path, low_memory=False))
            required = {"SYMBOL", "SERIES", "DELIV_PER", "DATE1"}
            if not required.issubset(frame.columns):
                raise ValueError(f"missing columns: {sorted(required - set(frame.columns))}")
            validate_delivery_report_date(frame, report_date.date(), source=f"Cache {path.name}")
            frame = frame[["SYMBOL", "SERIES", "DELIV_PER"]].copy()
            frame["SYMBOL"] = frame["SYMBOL"].astype(str).str.strip().str.upper()
            frame["SERIES"] = frame["SERIES"].astype(str).str.strip().str.upper()
            frame["DELIV_PER"] = pd.to_numeric(frame["DELIV_PER"], errors="coerce")
            frame = frame[(frame["SERIES"] == "EQ") & frame["DELIV_PER"].between(0, 100)]
            frame = frame.drop_duplicates(["SYMBOL", "SERIES"], keep="last")
            if frame.empty:
                raise ValueError("no valid EQ delivery rows")
            by_date[report_date.normalize()] = frame
        except Exception as exc:
            rejected.append(f"{path.name}: {exc}")
    return by_date, rejected


def _delivery_map(delivery_by_date: dict) -> tuple[dict, list]:
    lookup = {}
    issues = []
    for day, frame in delivery_by_date.items():
        required = {"SYMBOL", "DELIV_PER"}
        if not required.issubset(frame.columns):
            issues.append(f"{pd.Timestamp(day).date()}: delivery columns missing")
            continue
        rows = {}
        for symbol, value in zip(frame["SYMBOL"], frame["DELIV_PER"]):
            symbol = str(symbol).strip().upper()
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue
            if symbol and math.isfinite(value) and 0 <= value <= 100:
                if symbol in rows:
                    issues.append(f"{pd.Timestamp(day).date()}:{symbol}: duplicate delivery symbol")
                    rows.pop(symbol, None)
                else:
                    rows[symbol] = value
        lookup[pd.Timestamp(day).normalize()] = rows
    return lookup, issues


def run_backtest(price_dir: Path = PRICE_DIR, delivery_dir: Path = DELIVERY_DIR,
                 output_dir: Path = OUTPUT_DIR) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    prices, price_issues = _read_price_cache(price_dir)
    delivery_by_date, delivery_file_issues = _read_delivery_cache_strict(delivery_dir)
    delivery_lookup, delivery_row_issues = _delivery_map(delivery_by_date)
    price_files = list(price_dir.glob("bhavcopy_????????.csv")) if price_dir.exists() else []
    delivery_files = list(delivery_dir.glob("sec_bhavdata_full_????????.csv")) if delivery_dir.exists() else []

    coverage = {
        "PriceCacheFiles": len(price_files),
        "PriceDates": int(prices["DATE"].nunique()) if not prices.empty else 0,
        "PriceRows": int(len(prices)),
        "Symbols": int(prices["SYMBOL"].nunique()) if not prices.empty else 0,
        "EarliestPriceDate": str(prices["DATE"].min().date()) if not prices.empty else "",
        "LatestPriceDate": str(prices["DATE"].max().date()) if not prices.empty else "",
        "DeliveryCacheFiles": len(delivery_files),
        "DeliveryDates": len(delivery_by_date),
        "EarliestDeliveryDate": str(min(delivery_by_date).date()) if delivery_by_date else "",
        "LatestDeliveryDate": str(max(delivery_by_date).date()) if delivery_by_date else "",
        "PriceFileIssues": len(price_issues),
        "DeliveryFileIssues": len(delivery_file_issues) + len(delivery_row_issues),
        "NetworkCallsMade": False,
        "CacheModified": False,
        "MainboardPointInTimeUniverse": "NOT_AVAILABLE_EQ_SERIES_PROXY_ONLY",
        "FundamentalsPointInTime": "NOT_AVAILABLE_NOT_BACKTESTED",
        "EntryModel": "NEXT_OFFICIAL_SESSION_OPEN",
        "RoundTripCostBps": ROUND_TRIP_COST_BPS,
        "EntrySlippageBps": ENTRY_SLIPPAGE_BPS,
        "ExitSlippageBps": EXIT_SLIPPAGE_BPS,
        "StructuralStopTarget": "NOT_SIMULATED_NO_SYNTHETIC_STOP_OR_TARGET",
    }
    pd.DataFrame([coverage]).to_csv(output_dir / "cache_coverage.csv", index=False)
    pd.DataFrame({"Issue": price_issues + delivery_file_issues + delivery_row_issues}).to_csv(
        output_dir / "cache_file_issues.csv", index=False
    )
    if prices.empty or not delivery_lookup:
        pd.DataFrame([{"Status": "WAIT_FOR_DATA", "Reason": "Both valid price and delivery cache are required."}]).to_csv(output_dir / "comparison.csv", index=False)
        pd.DataFrame().to_csv(output_dir / "signals.csv", index=False)
        return {"status": "WAIT_FOR_DATA", "price_rows": len(prices), "delivery_dates": len(delivery_lookup)}

    prices = prices.sort_values(["DATE", "SYMBOL"]).reset_index(drop=True)
    prices["DATE"] = pd.to_datetime(prices["DATE"]).dt.normalize()
    market_dates = official_market_session_dates(prices["DATE"].min(), prices["DATE"].max())
    date_pos = {day: i for i, day in enumerate(market_dates)}
    official_date_set = set(market_dates)
    delivery_dates = sorted(d for d in delivery_lookup if d in official_date_set)
    records = []
    rejected = {
        "insufficient_44_session_history": 0,
        "missing_exact_prior_20_sessions": 0,
        "invalid_ohlcv_or_traded_value": 0,
        "delivery_wait_or_reject": 0,
        "delivery_stale_report": 0,
        "liquidity_below_1_5cr": 0,
        "type_a_conditions_not_met": 0,
        "missing_next_session_entry": 0,
        "overlapping_signal_observations": 0,
    }

    for symbol, raw in prices.groupby("SYMBOL", sort=True):
        f = raw.sort_values("DATE").drop_duplicates("DATE", keep=False).reset_index(drop=True)
        if f.empty:
            continue
        dates = pd.to_datetime(f["DATE"]).dt.normalize()
        idx_by_date = {day: i for i, day in enumerate(dates)}
        cols = {name: pd.to_numeric(f[name], errors="coerce").to_numpy(dtype=float)
                for name in ("OPEN", "HIGH", "LOW", "CLOSE", "VOLUME", "TRADED_VALUE")}
        close = cols["CLOSE"]
        high = cols["HIGH"]
        low = cols["LOW"]
        volume = cols["VOLUME"]
        traded = cols["TRADED_VALUE"]
        ema44 = pd.Series(close).ewm(span=44, adjust=False, min_periods=44).mean().to_numpy()

        for i, day in enumerate(dates):
            pos = date_pos.get(day, -1)
            if pos < MIN_WARMUP_BARS - 1:
                rejected["insufficient_44_session_history"] += 1
                continue
            # EMA44 is only accepted when all 44 official sessions (including
            # the signal date) exist for this symbol; no shortened warm-up.
            ema44_dates = market_dates[pos-(MIN_WARMUP_BARS-1):pos+1]
            if len(ema44_dates) != MIN_WARMUP_BARS or any(d not in idx_by_date for d in ema44_dates):
                rejected["insufficient_44_session_history"] += 1
                continue
            prior_dates = market_dates[pos-20:pos]
            prior_idx = [idx_by_date.get(d) for d in prior_dates]
            if len(prior_idx) != 20 or any(x is None for x in prior_idx):
                rejected["missing_exact_prior_20_sessions"] += 1
                continue
            prior_idx = np.asarray(prior_idx, dtype=int)
            values20 = traded[prior_idx]
            volumes20 = volume[prior_idx]
            current_values = [cols["OPEN"][i], high[i], low[i], close[i], volume[i], traded[i], ema44[i]]
            if (not np.isfinite(values20).all() or not np.isfinite(volumes20).all()
                or not np.isfinite(current_values).all() or (values20 < 0).any()
                or (volumes20 < 0).any() or close[i] <= 0 or low[i] <= 0
                or high[i] < low[i] or cols["OPEN"][i] <= 0 or ema44[i] <= 0
                or np.isnan(high[prior_idx]).any() or np.isnan(low[prior_idx]).any()
                or np.isnan(close[prior_idx]).any()
                or (high[prior_idx] <= 0).any() or (low[prior_idx] <= 0).any()
                or (close[prior_idx] <= 0).any()
                or low[i] > min(cols["OPEN"][i], close[i])
                or high[i] < max(cols["OPEN"][i], close[i])):
                rejected["invalid_ohlcv_or_traded_value"] += 1
                continue

            start = day - pd.Timedelta(days=29)
            candidate_days = [d for d in delivery_dates if start <= d <= day]
            if not candidate_days or (day - candidate_days[-1]).days > 7:
                rejected["delivery_stale_report"] += 1
                continue
            dvalues = [delivery_lookup[d][symbol] for d in candidate_days if symbol in delivery_lookup[d]]
            if len(dvalues) < 5:
                rejected["delivery_wait_or_reject"] += 1
                continue
            cat_a, cat_b = classify_delivery(dvalues)
            if cat_a != "PASS" and cat_b != "PASS":
                rejected["delivery_wait_or_reject"] += 1
                continue
            avg_traded_value = float(np.mean(values20))
            if avg_traded_value < LIQUIDITY_MIN_INR:
                rejected["liquidity_below_1_5cr"] += 1
                continue

            high20 = float(np.max(high[prior_idx]))
            if high20 <= 0:
                rejected["invalid_ohlcv_or_traded_value"] += 1
                continue
            correction = (high20 - close[i]) / high20 * 100.0
            near_ema44 = abs(close[i] - ema44[i]) / ema44[i] <= 0.03
            bullish_trend = close[i] > ema44[i]
            current_rvol = volume[i] / float(np.mean(volumes20)) if float(np.mean(volumes20)) > 0 else np.nan
            # The live helper compares the five most recent session volumes
            # (including current EOD) against the preceding 20-session average.
            five_idx = [idx_by_date.get(d) for d in market_dates[max(0, pos-4):pos+1]]
            if len(five_idx) != 5 or any(x is None for x in five_idx):
                rejected["missing_exact_prior_20_sessions"] += 1
                continue
            low_volume_days = int(np.sum(volume[np.asarray(five_idx, dtype=int)] < float(np.mean(volumes20))))
            candle_range = high[i] - low[i]
            clv = (close[i] - low[i]) / candle_range if candle_range > 0 else np.nan
            reversal = close[i] > cols["OPEN"][i] and close[i] > close[i-1] and clv > 0.50 if i > 0 else False

            if not (1.0 <= correction <= 15.0 and near_ema44 and bullish_trend
                    and np.isfinite(current_rvol) and current_rvol <= 1.5
                    and low_volume_days >= 3 and reversal):
                rejected["type_a_conditions_not_met"] += 1
                continue

            next_dates = forward_session_dates(market_dates, day, 1)
            if len(next_dates) != 1 or next_dates[0] not in idx_by_date:
                rejected["missing_next_session_entry"] += 1
                continue
            entry_idx = idx_by_date[next_dates[0]]
            entry_open = cols["OPEN"][entry_idx]
            if not np.isfinite(entry_open) or entry_open <= 0:
                rejected["missing_next_session_entry"] += 1
                continue
            entry_price = entry_open * (1 + ENTRY_SLIPPAGE_BPS / 10000.0)
            cost_pct = (ROUND_TRIP_COST_BPS + EXIT_SLIPPAGE_BPS) / 100.0
            rec = {
                "SignalDate": day.date().isoformat(), "Symbol": symbol,
                "DeliveryCategory": "A_AND_B" if cat_a == cat_b == "PASS" else "A_ONLY" if cat_a == "PASS" else "B_ONLY",
                "DeliveryValidReports": len(dvalues), "DeliveryAQualifyingWindows": sum(
                    sum(dvalues[j-4:j+1]) / 5.0 >= 60 for j in range(4, len(dvalues))),
                "DeliveryBQualifyingDays": sum(v >= 60 for v in dvalues),
                "AverageTradedValue20D_INR": avg_traded_value,
                "EMA44": float(ema44[i]), "Close": float(close[i]),
                "EMA44DistancePct": (close[i] / ema44[i] - 1) * 100,
                "CorrectionFrom20DHighPct": correction, "RVOL": current_rvol,
                "LowVolumeDays5D": low_volume_days, "CLV": clv,
                "EntryDate": next_dates[0].date().isoformat(),
                "EntryOpen": float(entry_open), "EntryPriceAfterEntrySlippage": entry_price,
                "RoundTripCostBps": ROUND_TRIP_COST_BPS,
                "EntrySlippageBps": ENTRY_SLIPPAGE_BPS, "ExitSlippageBps": EXIT_SLIPPAGE_BPS,
                "StopPrice": np.nan, "TargetPrice": np.nan, "RiskReward": np.nan,
                "RiskModelStatus": "NOT_SIMULATED_STRUCTURAL_LEVEL_REQUIRED",
            }
            for horizon in HORIZONS:
                future_dates = forward_session_dates(market_dates, next_dates[0], horizon)
                future_idx = [idx_by_date.get(d) for d in future_dates] if len(future_dates) == horizon else []
                complete = len(future_idx) == horizon and all(x is not None for x in future_idx)
                if complete:
                    fi = np.asarray(future_idx, dtype=int)
                    fh, fl, fc = high[fi], low[fi], close[fi]
                    complete = (np.isfinite(fh).all() and np.isfinite(fl).all()
                                and np.isfinite(fc).all() and (fh > 0).all()
                                and (fl > 0).all() and (fc > 0).all()
                                and (fl <= fh).all())
                if complete:
                    gross = (float(fc[-1]) / entry_price - 1) * 100
                    net = gross - cost_pct
                    rec[f"GrossReturn{horizon}D_Pct"] = gross
                    rec[f"NetReturn{horizon}D_Pct"] = net
                    rec[f"MFE{horizon}D_Pct"] = (float(np.max(fh)) / entry_price - 1) * 100
                    rec[f"MAE{horizon}D_Pct"] = (float(np.min(fl)) / entry_price - 1) * 100
                else:
                    rec[f"GrossReturn{horizon}D_Pct"] = np.nan
                    rec[f"NetReturn{horizon}D_Pct"] = np.nan
                    rec[f"MFE{horizon}D_Pct"] = np.nan
                    rec[f"MAE{horizon}D_Pct"] = np.nan
            records.append(rec)

    signals = pd.DataFrame(records)
    signals.to_csv(output_dir / "signals.csv", index=False)
    pd.DataFrame([{"Stage": k, "Rows": v} for k, v in rejected.items()]).to_csv(
        output_dir / "rejection_counts.csv", index=False
    )
    comparison = []
    for cohort in ("A_OR_B", "A_ONLY", "A_AND_B", "B_ONLY"):
        group = signals if cohort == "A_OR_B" else signals[
            signals.get("DeliveryCategory", pd.Series(dtype=str)).eq(cohort)
        ] if not signals.empty else signals
        row = {"DeliveryCohort": cohort, "SignalCount": int(len(group)),
               "EntryModel": "NEXT_OFFICIAL_SESSION_OPEN",
               "CostAssumptions": "Round-trip cost plus entry/exit slippage; configurable bps"}
        for horizon in HORIZONS:
            row.update(_summary(group.get(f"NetReturn{horizon}D_Pct", pd.Series(dtype=float)), f"Net{horizon}D"))
            row[f"AverageMFE{horizon}D_Pct"] = pd.to_numeric(group.get(f"MFE{horizon}D_Pct", pd.Series(dtype=float)), errors="coerce").mean()
            row[f"AverageMAE{horizon}D_Pct"] = pd.to_numeric(group.get(f"MAE{horizon}D_Pct", pd.Series(dtype=float)), errors="coerce").mean()
        row["RiskRewardStatus"] = "NOT_TESTED_NO_STRUCTURAL_STOP_TARGET"
        row["ResearchStatus"] = "RESEARCH_ONLY_NOT_PRODUCTION_VALIDATED"
        comparison.append(row)
    pd.DataFrame(comparison).to_csv(output_dir / "comparison.csv", index=False)
    result = {"status": "COMPLETE", "signals": len(signals), "price_rows": len(prices),
              "delivery_dates": len(delivery_lookup), "rejected": rejected}
    print(f"[EMA44 TYPE A BACKTEST] {result}")
    return result


if __name__ == "__main__":
    run_backtest()
