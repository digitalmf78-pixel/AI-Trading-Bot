"""Research-only technical momentum/VCP backtest on cached NSE EOD Bhavcopy.

All features are point-in-time: breakout highs exclude the signal session;
EMA and VCP blocks use only data through the signal EOD. Outcomes use the
next official session Open as the reference entry. No network or production
scanner integration.
"""
from __future__ import annotations

from pathlib import Path
import math
import numpy as np
import pandas as pd

from rsi_retest_existing_cache import _read_price_cache
from rvol_strategy_backtest import official_market_session_dates

PRICE_DIR = Path("data/bhavcopy")
OUTPUT_DIR = Path("outputs/technical_momentum_backtest")
LIQUIDITY_MIN_INR = 15_000_000.0
HORIZONS = (5, 10, 20)
SETUPS = (
    "ABOVE_EMA20", "EMA_STACK_20_44_50", "EMA_STACK_20_44_50_200", "ABOVE_EMA200",
    "BREAKOUT_20D", "BREAKOUT_50D", "BREAKOUT_100D",
    "VCP_TWO_CONTRACTIONS", "VCP_TWO_CONTRACTIONS_DRYUP",
    "EMA_STACK_AND_BREAKOUT20", "BREAKOUT20_AND_RVOL_1_5_5",
    "VCP_DRYUP_AND_BREAKOUT20",
)


def add_point_in_time_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Add causal features to a single symbol aligned to consecutive sessions."""
    f = frame.sort_values("DATE").copy().reset_index(drop=True)
    close = pd.to_numeric(f["CLOSE"], errors="coerce")
    high = pd.to_numeric(f["HIGH"], errors="coerce")
    low = pd.to_numeric(f["LOW"], errors="coerce")
    volume = pd.to_numeric(f["VOLUME"], errors="coerce")
    traded = pd.to_numeric(f["TRADED_VALUE"], errors="coerce")

    for span in (20, 44, 50, 200):
        f[f"EMA{span}"] = close.ewm(span=span, adjust=False, min_periods=span).mean()

    for window in (20, 50, 100):
        prior_high = high.rolling(window, min_periods=window).max().shift(1)
        f[f"PRIOR{window}D_HIGH"] = prior_high
        f[f"BREAKOUT_{window}D"] = close.gt(prior_high)

    f["RVOL20"] = volume / volume.shift(1).rolling(20, min_periods=20).mean()
    f["AVG_TRADED_VALUE20"] = traded.shift(1).rolling(20, min_periods=20).mean()
    f["LIQUIDITY_PASS"] = f["AVG_TRADED_VALUE20"].ge(LIQUIDITY_MIN_INR)
    f["ABOVE_EMA20"] = close.gt(f["EMA20"])
    f["EMA_STACK_20_44_50_200"] = (
        close.gt(f["EMA20"]) & f["EMA20"].gt(f["EMA44"])
        & f["EMA44"].gt(f["EMA50"]) & f["EMA50"].gt(f["EMA200"])
    )

    # Three consecutive 20-session blocks: 41-60 sessions ago, 21-40 ago,
    # and the latest 20 sessions including the signal EOD.
    widths = []
    block_volumes = []
    for shift in (40, 20, 0):
        block_high = high.rolling(20, min_periods=20).max().shift(shift)
        block_low = low.rolling(20, min_periods=20).min().shift(shift)
        widths.append((block_high / block_low - 1.0) * 100.0)
        block_volumes.append(volume.rolling(20, min_periods=20).mean().shift(shift))
    f["VCP_RANGE_WIDTH_1"] = widths[0]
    f["VCP_RANGE_WIDTH_2"] = widths[1]
    f["VCP_RANGE_WIDTH_3"] = widths[2]
    f["VCP_RATIO_2_VS_1"] = widths[1] / widths[0]
    f["VCP_RATIO_3_VS_2"] = widths[2] / widths[1]
    f["VCP_TWO_CONTRACTIONS"] = (
        widths[1].lt(widths[0]) & widths[2].lt(widths[1])
    )
    f["VOLUME_RATIO_3_VS_2"] = block_volumes[2] / block_volumes[1]
    f["VCP_DRYUP_LT_0_5"] = f["VOLUME_RATIO_3_VS_2"].lt(0.5)
    f["VCP_TWO_CONTRACTIONS_DRYUP"] = (
        f["VCP_TWO_CONTRACTIONS"] & f["VCP_DRYUP_LT_0_5"]
    )
    f["EMA_STACK_AND_BREAKOUT20"] = (
        f["EMA_STACK_20_44_50_200"] & f["BREAKOUT_20D"]
    )
    f["BREAKOUT20_AND_RVOL_1_5_5"] = (
        f["BREAKOUT_20D"] & f["RVOL20"].ge(1.5) & f["RVOL20"].lt(5.0)
    )
    f["VCP_DRYUP_AND_BREAKOUT20"] = (
        f["VCP_TWO_CONTRACTIONS_DRYUP"] & f["BREAKOUT_20D"]
    )
    f["FEATURES_MATURE"] = (
        f["COMPLETE_100_PRICE_SESSIONS"] & f["EMA50"].notna() & f["AVG_TRADED_VALUE20"].notna()
        & f["VCP_RANGE_WIDTH_1"].notna() & f["RVOL20"].notna()
    )
    return f


def _valid_future(frame: pd.DataFrame) -> bool:
    cols = ["OPEN", "HIGH", "LOW", "CLOSE"]
    values = frame[cols].apply(pd.to_numeric, errors="coerce")
    if values.isna().any().any() or not np.isfinite(values.to_numpy(dtype=float)).all():
        return False
    if (values <= 0).any().any() or (values["LOW"] > values["HIGH"]).any():
        return False
    return True


def _profit_factor(values: pd.Series) -> float:
    x = pd.to_numeric(values, errors="coerce").dropna()
    gains = float(x[x > 0].sum())
    losses = float(-x[x < 0].sum())
    if losses == 0:
        return float("inf") if gains > 0 else float("nan")
    return gains / losses


def _metric(group: pd.DataFrame, horizon: int) -> dict:
    ret = pd.to_numeric(group[f"Return{horizon}D_Pct"], errors="coerce").dropna()
    mfe = pd.to_numeric(group[f"MFE{horizon}D_Pct"], errors="coerce").dropna()
    out = {
        f"OutcomeN_{horizon}D": int(len(ret)),
        f"WinRate_{horizon}D_Pct": round(float(ret.gt(0).mean() * 100), 2) if len(ret) else np.nan,
        f"AverageReturn_{horizon}D_Pct": round(float(ret.mean()), 3) if len(ret) else np.nan,
        f"MedianReturn_{horizon}D_Pct": round(float(ret.median()), 3) if len(ret) else np.nan,
        f"ProfitFactor_{horizon}D": round(_profit_factor(ret), 3) if len(ret) and math.isfinite(_profit_factor(ret)) else _profit_factor(ret),
    }
    for threshold in (3, 5, 10, 15):
        out[f"MFE_GE_{threshold}Pct_{horizon}D_Pct"] = (
            round(float(mfe.ge(threshold).mean() * 100), 2) if len(mfe) else np.nan
        )
    return out


def run_backtest(price_dir: Path = PRICE_DIR, output_dir: Path = OUTPUT_DIR) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    prices, issues = _read_price_cache(price_dir)
    if prices.empty:
        pd.DataFrame([{"Status": "WAIT_FOR_DATA", "Reason": "No valid cached EQ Bhavcopy."}]).to_csv(output_dir / "comparison.csv", index=False)
        return {"status": "WAIT_FOR_DATA", "price_rows": 0}

    prices = prices.sort_values(["SYMBOL", "DATE"]).reset_index(drop=True)
    market_dates = official_market_session_dates(prices["DATE"].min(), prices["DATE"].max())
    date_pos = {d: i for i, d in enumerate(market_dates)}
    feature_rows = []
    outcome_rows = []
    duplicate_symbol_dates = int(prices.duplicated(["SYMBOL", "DATE"], keep=False).sum())

    for symbol, raw in prices.groupby("SYMBOL", sort=True):
        if raw["DATE"].duplicated().any():
            continue
        indexed = raw.set_index("DATE").reindex(market_dates)
        indexed.index.name = "DATE"
        indexed["DATE"] = indexed.index
        indexed["SYMBOL"] = symbol
        # A missing symbol session remains NaN and naturally blocks mature
        # rolling features; no forward-fill or synthetic candle is permitted.
        f = add_point_in_time_features(indexed.reset_index(drop=True))
        f["SYMBOL"] = symbol
        f["DATE"] = pd.to_datetime(f["DATE"])
        f = f[f["FEATURES_MATURE"] & f["LIQUIDITY_PASS"]].copy()
        if f.empty:
            continue
        for _, row in f.iterrows():
            active = [name for name in SETUPS if bool(row.get(name, False)) if pd.notna(row.get(name, False))]
            if not active:
                continue
            signal_date = pd.Timestamp(row["DATE"]).normalize()
            pos = date_pos.get(signal_date)
            if pos is None:
                continue
            rec = {
                "Date": signal_date.date().isoformat(), "Symbol": symbol,
                "Close": float(row["CLOSE"]), "RVOL20": float(row["RVOL20"]),
                "AvgTradedValue20D_INR": float(row["AVG_TRADED_VALUE20"]),
                "EMA20": row["EMA20"], "EMA44": row["EMA44"],
                "EMA50": row["EMA50"], "EMA200": row["EMA200"],
                "VCPRangeWidth1Pct": row["VCP_RANGE_WIDTH_1"],
                "VCPRangeWidth2Pct": row["VCP_RANGE_WIDTH_2"],
                "VCPRangeWidth3Pct": row["VCP_RANGE_WIDTH_3"],
                "VCPVolumeRatio3vs2": row["VOLUME_RATIO_3_VS_2"],
                "Setups": "|".join(active),
            }
            for setup in SETUPS:
                rec[setup] = bool(row.get(setup, False)) if pd.notna(row.get(setup, False)) else False
            for h in HORIZONS:
                future_dates = market_dates[pos + 1:pos + 1 + h]
                future = indexed.loc[future_dates] if len(future_dates) == h else pd.DataFrame()
                if len(future) == h and _valid_future(future):
                    entry = float(future.iloc[0]["OPEN"])
                    highs = pd.to_numeric(future["HIGH"], errors="coerce")
                    lows = pd.to_numeric(future["LOW"], errors="coerce")
                    close = float(future.iloc[-1]["CLOSE"])
                    rec[f"Return{h}D_Pct"] = (close / entry - 1.0) * 100.0
                    rec[f"MFE{h}D_Pct"] = (float(highs.max()) / entry - 1.0) * 100.0
                    rec[f"MAE{h}D_Pct"] = (float(lows.min()) / entry - 1.0) * 100.0
                    rec[f"OutcomeEndDate{h}D"] = future_dates[-1].date().isoformat()
                else:
                    rec[f"Return{h}D_Pct"] = np.nan
                    rec[f"MFE{h}D_Pct"] = np.nan
                    rec[f"MAE{h}D_Pct"] = np.nan
                    rec[f"OutcomeEndDate{h}D"] = ""
            feature_rows.append(rec)

    signals = pd.DataFrame(feature_rows)
    signals.to_csv(output_dir / "signals.csv", index=False)
    comparisons = []
    for setup in SETUPS:
        group = signals[signals[setup].eq(True)].copy() if not signals.empty else signals.copy()
        group = group.sort_values(["Symbol", "Date"])
        # For 20-session outcomes, retain no more than one event per symbol
        # in each 21-session interval; this is a descriptive de-overlap view.
        selected = []
        last_pos = {}
        for _, row in group.iterrows():
            day = pd.Timestamp(row["Date"])
            pos = date_pos.get(day, -10**9)
            if row["Symbol"] not in last_pos or pos - last_pos[row["Symbol"]] >= 21:
                selected.append(row)
                last_pos[row["Symbol"]] = pos
        nonoverlap = pd.DataFrame(selected)
        out = {
            "Setup": setup, "AllSignalRows": int(len(group)),
            "NonOverlappingSignals21Sessions": int(len(nonoverlap)),
            "FeatureScope": "EQ-series; prior-20-session average traded value >= INR 1.5 crore; no historical point-in-time Mainboard universe",
            "EntryReference": "Next official NSE session Open",
            "CostsSlippage": "Not included; not executable net returns",
        }
        for h in HORIZONS:
            out.update(_metric(nonoverlap, h))
        comparisons.append(out)
    comparison = pd.DataFrame(comparisons)
    comparison["BacktestStatus"] = "RESEARCH_ONLY_NOT_PRODUCTION_VALIDATED"
    comparison["MFEWarning"] = "MFE >=3/5/10/15% is maximum favorable excursion, not a realized booked return."
    comparison.to_csv(output_dir / "comparison.csv", index=False)
    coverage = {
        "PriceCacheFiles": len(list(price_dir.glob("bhavcopy_????????.csv"))),
        "PriceDates": int(prices["DATE"].nunique()),
        "PriceRows": int(len(prices)),
        "Symbols": int(prices["SYMBOL"].nunique()),
        "EarliestDate": str(prices["DATE"].min().date()),
        "LatestDate": str(prices["DATE"].max().date()),
        "OfficialSessions": len(market_dates),
        "DuplicateSymbolDateRows": duplicate_symbol_dates,
        "PriceFileIssues": len(issues),
        "NetworkCallsMade": False,
        "HistoricalMainboardUniverse": "NOT_AVAILABLE",
        "PointInTimeFundamentals": "NOT_AVAILABLE",
        "CostsSlippage": "NOT_INCLUDED",
        "MissingSymbolSessions": "NOT_FILLED; affected rolling windows/outcomes remain unavailable",
    }
    pd.DataFrame([coverage]).to_csv(output_dir / "cache_coverage.csv", index=False)
    pd.DataFrame({"Issue": issues}).to_csv(output_dir / "cache_file_issues.csv", index=False)
    print(comparison.to_string(index=False))
    print("[TECHNICAL MOMENTUM] Research only; no production filters or ranking changed.")
    return {"status": "OK", "signals": len(signals), "setups": len(comparison), "price_dates": len(market_dates)}


if __name__ == "__main__":
    run_backtest()
