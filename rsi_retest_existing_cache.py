"""Research-only RSI 30/40/50 retest comparison using ONLY restored NSE V8 cache files.

No network calls. Reads data/bhavcopy/bhavcopy_YYYYMMDD.csv and
 data/cache/delivery/sec_bhavdata_full_DDMMYYYY.csv. Produces signal and simple
 fixed-2R research reports. Fundamental data is reported separately and never
 guessed; this module is not wired into the production scanner.
"""
from __future__ import annotations
import re
from pathlib import Path
import pandas as pd

PRICE_DIR = Path("data/bhavcopy")
DELIVERY_DIR = Path("data/cache/delivery")
INPUT_DIR = Path("data/inputs")
OUT_DIR = Path("outputs/rsi_retest_existing_cache")
PRICE_RE = re.compile(r"bhavcopy_(\d{8})\.csv$", re.I)
DELIVERY_RE = re.compile(r"sec_bhavdata_full_(\d{8})\.csv$", re.I)


def _norm_cols(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [re.sub(r"[^A-Z0-9]+", "", str(c).strip().upper()) for c in out.columns]
    return out


def load_price_cache(price_dir: Path = PRICE_DIR) -> tuple[pd.DataFrame, list[str]]:
    files = sorted(price_dir.glob("bhavcopy_*.csv"))
    pieces, notes = [], []
    for path in files:
        m = PRICE_RE.search(path.name)
        if not m:
            continue
        try:
            raw = _norm_cols(pd.read_csv(path, low_memory=False))
        except Exception as exc:
            notes.append(f"PRICE_READ_ERROR {path.name}: {exc}")
            continue
        required = {"TCKRSYMB", "SCTYSRS", "OPNPRIC", "HG HPRIC".replace(" ", ""), "LWPRIC", "CLSPRIC"}
        if not required.issubset(raw.columns):
            notes.append(f"PRICE_SCHEMA_SKIP {path.name}: columns={','.join(raw.columns)}")
            continue
        df = pd.DataFrame({
            "Date": pd.to_datetime(m.group(1), format="%Y%m%d", errors="coerce"),
            "Symbol": raw["TCKRSYMB"].astype(str).str.strip().str.upper(),
            "Series": raw["SCTYSRS"].astype(str).str.strip().str.upper(),
            "Open": pd.to_numeric(raw["OPNPRIC"], errors="coerce"),
            "High": pd.to_numeric(raw["HG HPRIC".replace(" ", "")], errors="coerce"),
            "Low": pd.to_numeric(raw["LWPRIC"], errors="coerce"),
            "Close": pd.to_numeric(raw["CLSPRIC"], errors="coerce"),
        })
        # NSE equity series only; official main-board classification is separately audited.
        df = df[df["Series"].eq("EQ")]
        df = df.dropna(subset=["Date", "Symbol", "Open", "High", "Low", "Close"])
        df = df[(df[["Open", "High", "Low", "Close"]] > 0).all(axis=1)]
        if not df.empty:
            pieces.append(df[["Date", "Symbol", "Open", "High", "Low", "Close"]])
    if not pieces:
        return pd.DataFrame(columns=["Date", "Symbol", "Open", "High", "Low", "Close"]), notes
    all_prices = pd.concat(pieces, ignore_index=True)
    all_prices = all_prices.sort_values(["Symbol", "Date"]).drop_duplicates(["Symbol", "Date"], keep="last")
    return all_prices.reset_index(drop=True), notes


def load_delivery_cache(delivery_dir: Path = DELIVERY_DIR) -> tuple[pd.DataFrame, list[str]]:
    files = sorted(delivery_dir.glob("sec_bhavdata_full_*.csv"))
    pieces, notes = [], []
    for path in files:
        m = DELIVERY_RE.search(path.name)
        if not m:
            continue
        try:
            report_date = pd.to_datetime(m.group(1), format="%d%m%Y", errors="coerce")
            raw = _norm_cols(pd.read_csv(path, low_memory=False))
        except Exception as exc:
            notes.append(f"DELIVERY_READ_ERROR {path.name}: {exc}")
            continue
        if not {"SYMBOL", "DELIVPER"}.issubset(raw.columns):
            notes.append(f"DELIVERY_SCHEMA_SKIP {path.name}: columns={','.join(raw.columns)}")
            continue
        series = raw["SERIES"].astype(str).str.strip().str.upper() if "SERIES" in raw else pd.Series("EQ", index=raw.index)
        df = pd.DataFrame({
            "Date": report_date,
            "Symbol": raw["SYMBOL"].astype(str).str.strip().str.upper(),
            "Series": series,
            "DeliveryPct": pd.to_numeric(raw["DELIVPER"].astype(str).str.replace("%", "", regex=False), errors="coerce"),
        })
        df = df[df["Series"].eq("EQ")].dropna(subset=["Date", "Symbol", "DeliveryPct"])
        if not df.empty:
            pieces.append(df[["Date", "Symbol", "DeliveryPct"]])
    if not pieces:
        return pd.DataFrame(columns=["Date", "Symbol", "DeliveryPct"]), notes
    out = pd.concat(pieces, ignore_index=True).drop_duplicates(["Date", "Symbol"], keep="last")
    return out.sort_values(["Date", "Symbol"]).reset_index(drop=True), notes


def rsi_wilder(close: pd.Series, period: int = 14) -> pd.Series:
    close = pd.to_numeric(close, errors="coerce")
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - 100 / (1 + rs)
    rsi = rsi.mask((avg_loss == 0) & (avg_gain > 0), 100.0)
    rsi = rsi.mask((avg_loss == 0) & (avg_gain == 0), 50.0)
    return rsi


def add_indicators(prices: pd.DataFrame) -> pd.DataFrame:
    if prices.empty:
        return prices.assign(EMA50=pd.Series(dtype=float), RSI14=pd.Series(dtype=float), AboveEMA50=pd.Series(dtype=bool))
    parts = []
    for _, g in prices.groupby("Symbol", sort=False):
        g = g.sort_values("Date").copy()
        g["EMA50"] = g["Close"].ewm(span=50, adjust=False, min_periods=50).mean()
        g["RSI14"] = rsi_wilder(g["Close"], 14)
        g["AboveEMA50"] = g["Close"] > g["EMA50"]
        parts.append(g)
    return pd.concat(parts, ignore_index=True).sort_values(["Symbol", "Date"]).reset_index(drop=True)


def add_signals(frame: pd.DataFrame, lookback: int = 10) -> pd.DataFrame:
    parts = []
    for _, g in frame.groupby("Symbol", sort=False):
        g = g.sort_values("Date").copy()
        r = g["RSI14"]
        prev = r.shift(1)
        rising = r > prev
        # Defined research setups; signal is known only at the close of signal day.
        g["RSI30_RECOVERY"] = ((prev < 30) & (r >= 30) & rising & g["AboveEMA50"]).fillna(False)
        prior3 = r.shift(1).rolling(3, min_periods=1)
        touched40 = prior3.apply(lambda x: float(((x >= 38) & (x <= 42)).any()), raw=True).fillna(0).astype(bool)
        touched50 = prior3.apply(lambda x: float(((x >= 48) & (x <= 52)).any()), raw=True).fillna(0).astype(bool)
        reached40 = r.shift(1).rolling(lookback, min_periods=1).max() >= 43
        reached50 = r.shift(1).rolling(lookback, min_periods=1).max() >= 53
        g["RSI40_RETEST"] = (reached40 & touched40 & r.between(40, 45) & rising & g["AboveEMA50"]).fillna(False)
        g["RSI50_RETEST"] = (reached50 & touched50 & r.between(50, 55) & rising & g["AboveEMA50"]).fillna(False)
        parts.append(g)
    return pd.concat(parts, ignore_index=True).sort_values(["Symbol", "Date"]).reset_index(drop=True) if parts else frame.copy()


def delivery_gate(prices: pd.DataFrame, delivery: pd.DataFrame) -> pd.DataFrame:
    """Each of the five exact preceding price-session dates must have delivery >=60."""
    out = prices.copy()
    out["Delivery5Status"] = "WAIT_FOR_DATA"
    out["Delivery5Pass"] = False
    if delivery.empty or out.empty:
        return out
    lookup = {(pd.Timestamp(r.Date), str(r.Symbol)): float(r.DeliveryPct) for r in delivery.itertuples()}
    sessions = sorted(pd.Timestamp(x) for x in out["Date"].dropna().unique())
    session_pos = {d: i for i, d in enumerate(sessions)}
    for idx, row in out.iterrows():
        d = pd.Timestamp(row["Date"])
        pos = session_pos[d]
        if pos < 4:
            continue
        last5 = sessions[pos-4:pos+1]
        vals = [lookup.get((day, str(row["Symbol"]))) for day in last5]
        if any(v is None or pd.isna(v) for v in vals):
            out.at[idx, "Delivery5Status"] = "WAIT_FOR_DATA"
        elif all(v >= 60.0 for v in vals):
            out.at[idx, "Delivery5Status"] = "PASS"
            out.at[idx, "Delivery5Pass"] = True
        else:
            out.at[idx, "Delivery5Status"] = "REJECT"
    return out


def run_trade_simulation(frame: pd.DataFrame, signal_col: str, max_hold: int = 20) -> pd.DataFrame:
    """Exploratory next-open entry, signal-day low stop, 2R target, max 20 bars.
    If stop and target both hit in one bar, conservatively assume stop first.
    Signals without a next session, positive risk, or 20 future bars are marked
    OPEN/INSUFFICIENT_HORIZON rather than counted as closed wins/losses.
    """
    rows = []
    for symbol, g in frame.groupby("Symbol", sort=False):
        g = g.sort_values("Date").reset_index(drop=True)
        i = 0
        while i < len(g) - 1:
            if not bool(g.loc[i, signal_col]):
                i += 1
                continue
            entry_i = i + 1
            entry = float(g.loc[entry_i, "Open"])
            stop = float(g.loc[i, "Low"])
            risk = entry - stop
            base = {"Symbol": symbol, "Setup": signal_col, "SignalDate": g.loc[i, "Date"], "EntryDate": g.loc[entry_i, "Date"], "Entry": entry, "Stop": stop, "Target2R": entry + 2*risk}
            if risk <= 0:
                rows.append({**base, "ExitDate": pd.NaT, "Exit": float("nan"), "ExitReason": "INVALID_NONPOSITIVE_RISK", "PnL": float("nan"), "RMultiple": float("nan")})
                i += 1
                continue
            target = entry + 2*risk
            end = min(len(g)-1, entry_i + max_hold - 1)
            if entry_i + max_hold - 1 > len(g)-1:
                rows.append({**base, "ExitDate": pd.NaT, "Exit": float("nan"), "ExitReason": "INSUFFICIENT_HORIZON", "PnL": float("nan"), "RMultiple": float("nan")})
                i += 1
                continue
            exit_price, exit_date, reason = None, None, None
            for j in range(entry_i, end+1):
                lo, hi = float(g.loc[j, "Low"]), float(g.loc[j, "High"])
                if lo <= stop:  # conservative if stop and target both touched
                    exit_price, exit_date, reason = stop, g.loc[j, "Date"], "STOP_LOSS"
                    break
                if hi >= target:
                    exit_price, exit_date, reason = target, g.loc[j, "Date"], "TARGET_2R"
                    break
            if exit_price is None:
                exit_price, exit_date, reason = float(g.loc[end, "Close"]), g.loc[end, "Date"], "TIME_EXIT_20_SESSIONS"
            pnl = exit_price - entry
            rows.append({**base, "ExitDate": exit_date, "Exit": exit_price, "ExitReason": reason, "PnL": pnl, "RMultiple": pnl/risk})
            i = end + 1  # avoid overlapping trades for same symbol/setup
    return pd.DataFrame(rows)


def load_cached_board_symbols() -> tuple[set[str] | None, set[str] | None, str]:
    """Read official board classification only from restored cache; never fetch."""
    main_path = Path("data/cache/universe/nse_main_board_equity.csv")
    sme_path = Path("data/cache/universe/nse_sme_equity.csv")
    if not main_path.exists() or not sme_path.exists():
        return None, None, "WAIT_FOR_DATA_OFFICIAL_BOARD_CACHE_MISSING"
    try:
        main_df = _norm_cols(pd.read_csv(main_path, dtype=str))
        sme_df = _norm_cols(pd.read_csv(sme_path, dtype=str))
        def pick(df):
            for c in ("SYMBOL", "TCKRSYMB", "TRADINGSYMBOL", "SECURITYSYMBOL"):
                if c in df.columns:
                    vals = {str(v).strip().upper() for v in df[c].dropna() if str(v).strip()}
                    if vals:
                        return vals
            return set()
        main, sme = pick(main_df), pick(sme_df)
        if not main or not sme:
            return None, None, "WAIT_FOR_DATA_OFFICIAL_BOARD_CACHE_INVALID"
        return main, sme, "PASS_OFFICIAL_CACHED_CLASSIFICATION"
    except Exception:
        return None, None, "WAIT_FOR_DATA_OFFICIAL_BOARD_CACHE_INVALID"


def fundamental_data_status() -> tuple[str, int]:
    path = INPUT_DIR / "fundamental_metrics.csv"
    if not path.exists():
        return "WAIT_FOR_DATA_NO_FUNDAMENTAL_FILE", 0
    try:
        df = pd.read_csv(path)
    except Exception:
        return "WAIT_FOR_DATA_FUNDAMENTAL_FILE_UNREADABLE", 0
    if df.empty or len(df.columns) <= 1:
        return "WAIT_FOR_DATA_FUNDAMENTAL_METRICS_EMPTY", len(df)
    return "DATA_PRESENT_REQUIRES_THRESHOLD_AUDIT", len(df)


def run(output_dir: Path = OUT_DIR) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    prices, price_notes = load_price_cache()
    delivery, delivery_notes = load_delivery_cache()
    main_symbols, sme_symbols, board_status = load_cached_board_symbols()
    if not prices.empty and main_symbols is not None and sme_symbols is not None:
        before = len(prices)
        prices = prices[prices["Symbol"].isin(main_symbols) & ~prices["Symbol"].isin(sme_symbols)].copy()
        price_notes.append(f"OFFICIAL_MAIN_BOARD_CACHE_FILTER input_rows={before} output_rows={len(prices)}")
    coverage = {
        "price_cache_files": len(list(PRICE_DIR.glob("bhavcopy_*.csv"))) if PRICE_DIR.exists() else 0,
        "price_rows": len(prices), "symbols_with_prices": int(prices["Symbol"].nunique()) if not prices.empty else 0,
        "price_sessions": int(prices["Date"].nunique()) if not prices.empty else 0,
        "first_price_date": str(prices["Date"].min().date()) if not prices.empty else "NONE",
        "last_price_date": str(prices["Date"].max().date()) if not prices.empty else "NONE",
        "delivery_cache_files": len(list(DELIVERY_DIR.glob("sec_bhavdata_full_*.csv"))) if DELIVERY_DIR.exists() else 0,
        "delivery_rows": len(delivery), "delivery_sessions": int(delivery["Date"].nunique()) if not delivery.empty else 0,
        "fundamental_status": fundamental_data_status()[0], "fundamental_rows": fundamental_data_status()[1],
        "official_board_status": board_status,
        "no_network_calls": True,
    }
    pd.DataFrame([coverage]).to_csv(output_dir / "cache_coverage.csv", index=False)
    (output_dir / "cache_diagnostics.txt").write_text("\n".join([str(coverage), *price_notes, *delivery_notes]), encoding="utf-8")
    if prices.empty:
        pd.DataFrame(columns=["Setup", "RawSignals", "DeliveryPassSignals", "DeliveryWaitSignals", "ClosedTrades", "WinRatePct", "NetR", "MaxDrawdownR"]).to_csv(output_dir / "rsi_retest_comparison.csv", index=False)
        return {"coverage": coverage, "status": "NO_LOCAL_BHAVCOPY_CACHE_FILES"}
    indicators = add_indicators(prices)
    signals = add_signals(indicators)
    gated = delivery_gate(signals, delivery)
    fundamentals_status, _ = fundamental_data_status()
    gated["FundamentalGateStatus"] = fundamentals_status
    gated["FundamentalGatePass"] = False  # never infer quality from missing/unapproved inputs
    signal_cols = ["RSI30_RECOVERY", "RSI40_RETEST", "RSI50_RETEST"]
    summaries, trades_all = [], []
    for col in signal_cols:
        raw_n = int(signals[col].sum())
        delivery_pass_n = int((gated[col] & gated["Delivery5Pass"]).sum())
        delivery_wait_n = int((gated[col] & gated["Delivery5Status"].eq("WAIT_FOR_DATA")).sum())
        # Technical-only exploratory P&L comparison, explicitly not fundamental-qualified picks.
        trades = run_trade_simulation(signals, col)
        if not trades.empty:
            trades_all.append(trades)
        closed = trades[trades["ExitReason"].isin(["STOP_LOSS", "TARGET_2R", "TIME_EXIT_20_SESSIONS"])] if not trades.empty else pd.DataFrame()
        r = pd.to_numeric(closed.get("RMultiple", pd.Series(dtype=float)), errors="coerce").dropna()
        wins = int((r > 0).sum())
        # Peak-to-trough drawdown in cumulative R for closed trades, chronological order.
        if not closed.empty and "ExitDate" in closed.columns:
            closed = closed.sort_values("ExitDate", kind="mergesort")
            r = pd.to_numeric(closed["RMultiple"], errors="coerce").dropna()
        cum = r.cumsum()
        dd = (cum - cum.cummax()) if len(cum) else pd.Series(dtype=float)
        summaries.append({"Setup": col, "RawSignals": raw_n, "DeliveryPassSignals": delivery_pass_n,
                          "DeliveryWaitSignals": delivery_wait_n, "FundamentalQualifiedSignals": 0,
                          "FundamentalStatus": fundamentals_status, "ClosedTrades": len(closed),
                          "WinRatePct": round(100*wins/len(closed), 2) if len(closed) else None,
                          "NetR": round(float(r.sum()), 3) if len(r) else None,
                          "MaxDrawdownR": round(float(dd.min()), 3) if len(dd) else None,
                          "PnlScope": "TECHNICAL_ONLY_RESEARCH_NOT_FULL_STRATEGY"})
    signals.to_csv(output_dir / "rsi_retest_all_technical_signals.csv", index=False)
    gated.to_csv(output_dir / "rsi_retest_delivery_audit.csv", index=False)
    pd.DataFrame(summaries).to_csv(output_dir / "rsi_retest_comparison.csv", index=False)
    if trades_all:
        pd.concat(trades_all, ignore_index=True).to_csv(output_dir / "rsi_retest_trade_log.csv", index=False)
    return {"coverage": coverage, "status": "COMPLETED_TECHNICAL_RESEARCH", "summary": summaries}


if __name__ == "__main__":
    result = run()
    print(result)
