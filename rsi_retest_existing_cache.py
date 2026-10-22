"""Research-only RSI retest comparison using the repository's existing NSE cache.

No network calls are made. Historical results use cached EOD bhavcopy and, where
available, cached delivery reports. Point-in-time historical fundamentals are not
available in this project cache, so the report explicitly does not claim that the
fundamental gate was backtested.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable
import numpy as np
import pandas as pd

PRICE_DIR = Path("data/bhavcopy")
DELIVERY_DIR = Path("data/cache/delivery")
OUTPUT_DIR = Path("outputs/rsi_retest")
EMA_SPAN = 50
RSI_PERIOD = 14
FORWARD_SESSIONS = (5, 10)
MIN_DELIVERY_PCT = 60.0


def _norm_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).strip().upper().replace(" ", "_") for c in out.columns]
    return out


def _read_price_cache(price_dir: Path = PRICE_DIR) -> tuple[pd.DataFrame, list[str]]:
    files = sorted(price_dir.glob("bhavcopy_????????.csv"))
    frames = []
    rejected = []
    for path in files:
        m = re.fullmatch(r"bhavcopy_(\d{8})\.csv", path.name)
        if not m:
            continue
        date = pd.to_datetime(m.group(1), format="%Y%m%d", errors="coerce")
        if pd.isna(date):
            rejected.append(f"{path.name}: invalid filename date")
            continue
        try:
            df = _norm_columns(pd.read_csv(path, low_memory=False))
        except Exception as exc:
            rejected.append(f"{path.name}: read error: {exc}")
            continue
        # CM-UDiFF columns used by the live scanner.
        symbol_col = "TCKRSYMB" if "TCKRSYMB" in df else "SYMBOL" if "SYMBOL" in df else None
        series_col = "SCTYSRS" if "SCTYSRS" in df else "SERIES" if "SERIES" in df else None
        close_col = "CLSPRIC" if "CLSPRIC" in df else "CLOSE" if "CLOSE" in df else None
        if not symbol_col or not series_col or not close_col:
            rejected.append(f"{path.name}: required symbol/series/close columns missing")
            continue
        rename = {symbol_col: "SYMBOL", series_col: "SERIES", close_col: "CLOSE"}
        for old, new in [("OPNPRIC", "OPEN"), ("HGHPRIC", "HIGH"), ("LWPRIC", "LOW"), ("TTLTRADGVOL", "VOLUME"), ("TTLTRFVAL", "TRADED_VALUE")]:
            if old in df.columns:
                rename[old] = new
        df = df.rename(columns=rename)
        for col in ("OPEN", "HIGH", "LOW", "VOLUME", "TRADED_VALUE"):
            if col not in df:
                df[col] = np.nan
        df["DATE"] = date.normalize()
        df["SYMBOL"] = df["SYMBOL"].astype(str).str.strip().str.upper()
        df["SERIES"] = df["SERIES"].astype(str).str.strip().str.upper()
        for col in ("OPEN", "HIGH", "LOW", "CLOSE", "VOLUME", "TRADED_VALUE"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df[(df["SERIES"] == "EQ") & df["SYMBOL"].ne("") & df["CLOSE"].gt(0)]
        if df.empty:
            rejected.append(f"{path.name}: no valid EQ price rows")
            continue
        df = df[["DATE", "SYMBOL", "SERIES", "OPEN", "HIGH", "LOW", "CLOSE", "VOLUME", "TRADED_VALUE"]]
        frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["DATE", "SYMBOL", "SERIES", "OPEN", "HIGH", "LOW", "CLOSE", "VOLUME", "TRADED_VALUE"]), rejected
    all_prices = pd.concat(frames, ignore_index=True)
    all_prices = all_prices.drop_duplicates(["DATE", "SYMBOL", "SERIES"], keep="last")
    all_prices = all_prices.sort_values(["SYMBOL", "DATE"]).reset_index(drop=True)
    return all_prices, rejected


def _read_delivery_cache(delivery_dir: Path = DELIVERY_DIR) -> tuple[dict[pd.Timestamp, pd.DataFrame], list[str]]:
    files = sorted(delivery_dir.glob("sec_bhavdata_full_????????.csv"))
    by_date: dict[pd.Timestamp, pd.DataFrame] = {}
    rejected = []
    for path in files:
        m = re.fullmatch(r"sec_bhavdata_full_(\d{8})\.csv", path.name)
        if not m:
            continue
        date = pd.to_datetime(m.group(1), format="%d%m%Y", errors="coerce")
        if pd.isna(date):
            rejected.append(f"{path.name}: invalid delivery filename date")
            continue
        try:
            df = _norm_columns(pd.read_csv(path, low_memory=False))
        except Exception as exc:
            rejected.append(f"{path.name}: read error: {exc}")
            continue
        required = {"SYMBOL", "SERIES", "DELIV_PER"}
        if not required.issubset(df.columns):
            rejected.append(f"{path.name}: required delivery columns missing")
            continue
        df = df[["SYMBOL", "SERIES", "DELIV_PER"]].copy()
        df["SYMBOL"] = df["SYMBOL"].astype(str).str.strip().str.upper()
        df["SERIES"] = df["SERIES"].astype(str).str.strip().str.upper()
        df["DELIV_PER"] = pd.to_numeric(df["DELIV_PER"], errors="coerce")
        df = df[(df["SERIES"] == "EQ") & df["DELIV_PER"].between(0, 100)]
        df = df.drop_duplicates(["SYMBOL", "SERIES"], keep="last")
        if not df.empty:
            by_date[date.normalize()] = df
    return by_date, rejected


def _rsi(series: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    delta = series.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)
    avg_gain = gains.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = losses.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    # Monotonic rising price series has RSI 100, not missing.
    rsi = rsi.mask((avg_loss == 0) & (avg_gain > 0), 100.0)
    rsi = rsi.mask((avg_gain == 0) & (avg_loss > 0), 0.0)
    return rsi


def _delivery_status(symbol: str, signal_date: pd.Timestamp, delivery_by_date: dict[pd.Timestamp, pd.DataFrame]) -> tuple[str, int, float | None]:
    dates = sorted(d for d in delivery_by_date if d <= signal_date)[-5:]
    if len(dates) < 5:
        return "WAIT_FOR_DATA", len(dates), None
    values = []
    for day in dates:
        frame = delivery_by_date[day]
        hit = frame.loc[frame["SYMBOL"].eq(symbol), "DELIV_PER"]
        if hit.empty or pd.isna(hit.iloc[-1]):
            return "WAIT_FOR_DATA", len(dates), None
        values.append(float(hit.iloc[-1]))
    if all(v >= MIN_DELIVERY_PCT for v in values):
        return "PASS_GE_60_EACH_OF_5", 5, min(values)
    return "REJECT_LT_60_IN_ANY_OF_5", 5, min(values)


def _signals_for_symbol(frame: pd.DataFrame) -> pd.DataFrame:
    f = frame.sort_values("DATE").copy().reset_index(drop=True)
    # EMA is calculated from the earliest available close so the existing ~50-session
    # cache can still be explored. Early values are explicitly marked as warm-up.
    f["EMA50"] = f["CLOSE"].ewm(span=EMA_SPAN, adjust=False, min_periods=1).mean()
    f["EMA50Bars"] = np.arange(1, len(f) + 1)
    f["EMA50WarmupStatus"] = np.where(f["EMA50Bars"] >= EMA_SPAN, "MATURE_50_PLUS_BARS", "PRELIMINARY_LESS_THAN_50_BARS")
    f["RSI14"] = _rsi(f["CLOSE"], RSI_PERIOD)
    f["ABOVE_EMA50"] = f["CLOSE"] > f["EMA50"]
    r = f["RSI14"]
    prev = r.shift(1)
    prev2 = r.shift(2)
    f["RSI30_RECOVERY"] = prev.le(30) & r.gt(30)
    # Prior session retested 40 zone after a stronger reading; current session turns up.
    f["RSI40_RETEST"] = prev2.ge(43) & prev.between(38, 42, inclusive="both") & r.gt(prev) & r.ge(40)
    # Prior session retested 50 zone after a stronger reading; current session turns up.
    f["RSI50_RETEST"] = prev2.ge(53) & prev.between(48, 52, inclusive="both") & r.gt(prev) & r.ge(50)
    return f


def _metrics(prefix: str, values: pd.Series, row: dict) -> None:
    vals = pd.to_numeric(values, errors="coerce").dropna()
    for horizon in FORWARD_SESSIONS:
        col = f"ForwardReturn{horizon}D_Pct"
        # This helper receives one return series at a time, so the caller adds horizon-specific metrics.
        pass


def _summarize(name: str, signals: pd.DataFrame, delivery_passed: pd.DataFrame) -> dict:
    row = {"Setup": name, "TechnicalSignals": int(len(signals)),
           "DeliveryPassSignals": int(len(delivery_passed)),
           "DeliveryRejectedSignals": int((signals.get("DeliveryStatus", pd.Series(dtype=str)) == "REJECT_LT_60_IN_ANY_OF_5").sum()),
           "DeliveryWaitSignals": int((signals.get("DeliveryStatus", pd.Series(dtype=str)) == "WAIT_FOR_DATA").sum()),
           "FundamentalBacktestStatus": "NOT_BACKTESTED_NO_POINT_IN_TIME_FUNDAMENTAL_HISTORY",
           "PrimaryMetricsScope": "TECHNICAL_ONLY; historical delivery/fundamental gates may be unavailable"}
    for horizon in FORWARD_SESSIONS:
        col = f"ForwardReturn{horizon}D_Pct"
        vals = pd.to_numeric(signals.get(col, pd.Series(dtype=float)), errors="coerce").dropna()
        row[f"TradesWith{horizon}DOutcome"] = int(len(vals))
        row[f"WinRate{horizon}D_Pct"] = round(float((vals > 0).mean() * 100), 2) if len(vals) else np.nan
        row[f"AverageReturn{horizon}D_Pct"] = round(float(vals.mean()), 3) if len(vals) else np.nan
        row[f"MedianReturn{horizon}D_Pct"] = round(float(vals.median()), 3) if len(vals) else np.nan
        wins = vals[vals > 0].sum()
        losses = -vals[vals < 0].sum()
        row[f"ProfitFactor{horizon}D"] = round(float(wins / losses), 3) if losses > 0 else (np.inf if wins > 0 else np.nan)
        qvals = pd.to_numeric(delivery_passed.get(col, pd.Series(dtype=float)), errors="coerce").dropna()
        row[f"DeliveryQualifiedTradesWith{horizon}DOutcome"] = int(len(qvals))
        row[f"DeliveryQualifiedWinRate{horizon}D_Pct"] = round(float((qvals > 0).mean() * 100), 2) if len(qvals) else np.nan
        row[f"DeliveryQualifiedAverageReturn{horizon}D_Pct"] = round(float(qvals.mean()), 3) if len(qvals) else np.nan
    return row


def run_backtest(price_dir: Path = PRICE_DIR, delivery_dir: Path = DELIVERY_DIR, output_dir: Path = OUTPUT_DIR) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    prices, bad_price_files = _read_price_cache(price_dir)
    delivery_by_date, bad_delivery_files = _read_delivery_cache(delivery_dir)
    coverage = pd.DataFrame([{
        "PriceCacheFiles": len(list(price_dir.glob("bhavcopy_????????.csv"))) if price_dir.exists() else 0,
        "PriceDates": int(prices["DATE"].nunique()) if not prices.empty else 0,
        "PriceRows": int(len(prices)),
        "SymbolsWithPriceData": int(prices["SYMBOL"].nunique()) if not prices.empty else 0,
        "EarliestPriceDate": str(prices["DATE"].min().date()) if not prices.empty else "",
        "LatestPriceDate": str(prices["DATE"].max().date()) if not prices.empty else "",
        "DeliveryCacheFiles": len(list(delivery_dir.glob("sec_bhavdata_full_????????.csv"))) if delivery_dir.exists() else 0,
        "DeliveryDates": len(delivery_by_date),
        "EarliestDeliveryDate": str(min(delivery_by_date).date()) if delivery_by_date else "",
        "LatestDeliveryDate": str(max(delivery_by_date).date()) if delivery_by_date else "",
        "PriceFileIssues": len(bad_price_files), "DeliveryFileIssues": len(bad_delivery_files),
        "NetworkCallsMade": False,
        "FundamentalHistoricalDataAvailable": False,
        "Notes": "Existing cache only; no network calls. Historical fundamental data is not point-in-time, so fundamental filter is not claimed as backtested."
    }])
    coverage.to_csv(output_dir / "cache_coverage.csv", index=False)
    pd.DataFrame({"Issue": bad_price_files + bad_delivery_files}).to_csv(output_dir / "cache_file_issues.csv", index=False)
    if prices.empty:
        empty = pd.DataFrame(columns=["Date", "Symbol", "Setup", "Close", "EMA50", "RSI14", "DeliveryStatus"])
        empty.to_csv(output_dir / "rsi_retest_signals.csv", index=False)
        pd.DataFrame([{"Status": "WAIT_FOR_DATA", "Reason": "No valid cached daily EQ bhavcopy files found; network access intentionally disabled."}]).to_csv(output_dir / "rsi_retest_comparison.csv", index=False)
        empty.to_csv(output_dir / "rsi_retest_current_watchlist.csv", index=False)
        print("[RSI RETEST] WAIT_FOR_DATA: no valid existing price cache files found.")
        return {"status": "WAIT_FOR_DATA", "price_rows": 0}

    all_rows = []
    for symbol, raw in prices.groupby("SYMBOL", sort=True):
        f = _signals_for_symbol(raw)
        # Evaluate only sessions where 50 EMA is available, plus RSI values.
        valid = f["EMA50"].notna() & f["RSI14"].notna() & f["ABOVE_EMA50"]
        for setup, flag in [("RSI30_RECOVERY", "RSI30_RECOVERY"), ("RSI40_RETEST", "RSI40_RETEST"), ("RSI50_RETEST", "RSI50_RETEST")]:
            idxs = f.index[valid & f[flag].fillna(False)]
            for idx in idxs:
                row = f.loc[idx]
                signal_date = pd.Timestamp(row["DATE"]).normalize()
                dstatus, dcount, dmin = _delivery_status(symbol, signal_date, delivery_by_date)
                rec = {"Date": signal_date.date().isoformat(), "Symbol": symbol, "Setup": setup,
                       "Close": float(row["CLOSE"]), "EMA50": float(row["EMA50"]),
                       "EMA50Bars": int(row["EMA50Bars"]), "EMA50WarmupStatus": str(row["EMA50WarmupStatus"]),
                       "RSI14": float(row["RSI14"]),
                       "PreviousRSI14": float(f.loc[idx-1, "RSI14"]) if idx >= 1 and pd.notna(f.loc[idx-1, "RSI14"]) else np.nan,
                       "DeliveryStatus": dstatus, "DeliverySessions": dcount, "MinimumDelivery5D_Pct": dmin,
                       "FundamentalStatus": "NOT_BACKTESTED_NO_POINT_IN_TIME_FUNDAMENTAL_HISTORY"}
                for horizon in FORWARD_SESSIONS:
                    future_idx = idx + horizon
                    rec[f"ForwardReturn{horizon}D_Pct"] = (float(f.loc[future_idx, "CLOSE"]) / float(row["CLOSE"]) - 1) * 100 if future_idx < len(f) else np.nan
                    # max adverse/favorable excursion based on daily low/high over next N sessions.
                    if future_idx < len(f):
                        future = f.loc[idx+1:future_idx]
                        rec[f"MaxAdverse{horizon}D_Pct"] = (float(future["LOW"].min()) / float(row["CLOSE"]) - 1) * 100 if future["LOW"].notna().any() else np.nan
                        rec[f"MaxFavorable{horizon}D_Pct"] = (float(future["HIGH"].max()) / float(row["CLOSE"]) - 1) * 100 if future["HIGH"].notna().any() else np.nan
                    else:
                        rec[f"MaxAdverse{horizon}D_Pct"] = np.nan
                        rec[f"MaxFavorable{horizon}D_Pct"] = np.nan
                all_rows.append(rec)
    signals = pd.DataFrame(all_rows)
    if signals.empty:
        signals = pd.DataFrame(columns=["Date", "Symbol", "Setup", "Close", "EMA50", "RSI14", "PreviousRSI14", "DeliveryStatus", "DeliverySessions", "MinimumDelivery5D_Pct", "FundamentalStatus", "ForwardReturn5D_Pct", "ForwardReturn10D_Pct"])
    signals.to_csv(output_dir / "rsi_retest_signals.csv", index=False)
    # Performance only uses signals that have confirmed delivery qualification. Signals with
    # incomplete delivery history or rejected delivery are not counted as qualifying trades.
    comparison = []
    for setup in ("RSI30_RECOVERY", "RSI40_RETEST", "RSI50_RETEST"):
        raw = signals[signals["Setup"].eq(setup)].copy() if not signals.empty else signals.copy()
        qualified = raw[raw["DeliveryStatus"].eq("PASS_GE_60_EACH_OF_5")].copy() if not raw.empty else raw
        comparison.append(_summarize(setup, raw, qualified))
    comp = pd.DataFrame(comparison)
    comp["BacktestStatus"] = np.where(comp["TradesWith5DOutcome"].fillna(0).gt(0), "TECHNICAL_ONLY_PRELIMINARY", "WAIT_FOR_DATA")
    comp["RiskNote"] = "Primary returns are technical-only and may include EMA50 warm-up bars; delivery-qualified metrics are separate. No point-in-time fundamentals, transaction costs, or slippage. Do not use as production rule without a longer cache and validation."
    comp.to_csv(output_dir / "rsi_retest_comparison.csv", index=False)
    latest = prices["DATE"].max()
    current = signals[signals["Date"].eq(latest.date().isoformat())].copy() if not signals.empty else signals.copy()
    current.to_csv(output_dir / "rsi_retest_current_watchlist.csv", index=False)
    print(f"[RSI RETEST] Cache dates={prices['DATE'].nunique()}, symbols={prices['SYMBOL'].nunique()}, signals={len(signals)}")
    print(f"[RSI RETEST] Reports: {output_dir}/rsi_retest_comparison.csv, rsi_retest_signals.csv, cache_coverage.csv")
    print("[RSI RETEST] Historical fundamentals not backtested: no point-in-time fundamental dataset available.")
    print("[RSI RETEST] EMA50 warm-up status is included per signal; results from fewer than 50 bars are preliminary.")
    return {"status": "OK", "price_rows": int(len(prices)), "signals": int(len(signals))}


if __name__ == "__main__":
    run_backtest()
