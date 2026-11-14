"""Research-only chronological walk-forward and four-slot portfolio simulation.

This is a temporal robustness check on the existing cached sample, not a clean
untouched out-of-sample test: candidate rules were identified after viewing the
earlier full-sample comparison. It never changes the production scanner.
"""
from pathlib import Path
import math
import numpy as np
import pandas as pd

SIGNALS = Path("outputs/delivery_momentum_research/signals_with_delivery.csv")
SESSIONS = Path("outputs/technical_momentum_backtest/market_sessions.csv")
OUT = Path("outputs/walk_forward_momentum_validation")
CAPITAL = 100_000.0
POSITION_SIZE = 25_000.0
MAX_POSITIONS = 4
COST_BPS = (0, 25, 50)
HORIZONS = (5, 10, 20)

STRATEGIES = {
    "AB_RVOL_LIQ_EMA_STACK": lambda d: (
        d["DeliveryABStatus"].isin(["A_ONLY", "B_ONLY", "A_AND_B"])
        & d["RVOL20"].ge(1.5) & d["RVOL20"].lt(5.0)
        & d["AvgTradedValue20D_INR"].ge(20_000_000)
        & d["AvgTradedValue20D_INR"].lt(50_000_000)
        & d["EMA_STACK_20_44_50"].astype(bool)
    ),
    "AB_RVOL_LIQ_BREAKOUT20": lambda d: (
        d["DeliveryABStatus"].isin(["A_ONLY", "B_ONLY", "A_AND_B"])
        & d["RVOL20"].ge(1.5) & d["RVOL20"].lt(5.0)
        & d["AvgTradedValue20D_INR"].ge(20_000_000)
        & d["AvgTradedValue20D_INR"].lt(50_000_000)
        & d["BREAKOUT_20D"].astype(bool)
    ),
}


def make_folds(sessions, start_idx, end_idx, train_len=20, embargo=20, test_len=20):
    """Two expanding-window folds, with a 20-session purge before each test."""
    available = end_idx - start_idx + 1
    folds = []
    cursor = start_idx
    fold_no = 1
    while cursor + train_len + embargo + test_len - 1 <= end_idx:
        train_start = cursor
        train_end = cursor + train_len - 1
        test_start = train_end + embargo + 1
        test_end = test_start + test_len - 1
        folds.append({
            "Fold": f"WF{fold_no}",
            "TrainStart": sessions[train_start],
            "TrainEnd": sessions[train_end],
            "EmbargoStart": sessions[train_end + 1],
            "EmbargoEnd": sessions[test_start - 1],
            "TestStart": sessions[test_start],
            "TestEnd": sessions[test_end],
            "train_start_idx": train_start,
            "train_end_idx": train_end,
            "test_start_idx": test_start,
            "test_end_idx": test_end,
        })
        cursor = test_start
        fold_no += 1
    return folds


def non_overlapping(frame, session_pos, min_gap=21):
    """Keep the first signal per symbol, then require 21 actual NSE sessions."""
    if frame.empty:
        return frame.copy()
    kept = []
    last = {}
    for _, row in frame.sort_values(["Symbol", "Date", "RVOL20"], ascending=[True, True, False]).iterrows():
        idx = session_pos[row["Date"]]
        symbol = row["Symbol"]
        if symbol not in last or idx - last[symbol] >= min_gap:
            kept.append(row)
            last[symbol] = idx
    return pd.DataFrame(kept).reset_index(drop=True)


def _pf(values):
    x = pd.to_numeric(pd.Series(values), errors="coerce").dropna()
    gains = float(x[x > 0].sum())
    losses = float(-x[x < 0].sum())
    return gains / losses if losses else (math.inf if gains else np.nan)


def outcome_metrics(frame, horizon):
    col = f"Return{horizon}D_Pct"
    x = pd.to_numeric(frame[col], errors="coerce").dropna()
    return {
        "N": int(len(x)),
        "WinRatePct": round(float(x.gt(0).mean() * 100), 2) if len(x) else np.nan,
        "AverageReturnPct": round(float(x.mean()), 3) if len(x) else np.nan,
        "MedianReturnPct": round(float(x.median()), 3) if len(x) else np.nan,
        "ProfitFactor": round(_pf(x), 3) if len(x) and math.isfinite(_pf(x)) else _pf(x),
    }


def simulate_portfolio(frame, sessions, horizon, cost_bps=0):
    """Fixed ₹25k slots; next-session Open entry, horizon-close exit, no leverage."""
    entry_col = f"EntryDate{horizon}D"
    exit_col = f"OutcomeEndDate{horizon}D"
    return_col = f"Return{horizon}D_Pct"
    d = frame.copy()
    d[entry_col] = pd.to_datetime(d[entry_col], errors="coerce")
    d[exit_col] = pd.to_datetime(d[exit_col], errors="coerce")
    d[return_col] = pd.to_numeric(d[return_col], errors="coerce")
    d = d.dropna(subset=[entry_col, exit_col, return_col])
    d = d.sort_values([entry_col, "RVOL20", "AvgTradedValue20D_INR", "Symbol"],
                      ascending=[True, False, False, True])
    session_pos = {pd.Timestamp(x): i for i, x in enumerate(sessions)}
    by_entry = {}
    for row in d.to_dict("records"):
        by_entry.setdefault(row[entry_col], []).append(row)

    cash = CAPITAL
    open_positions = []
    completed = []
    cost_rate = cost_bps / 10_000.0
    for day in sessions:
        day = pd.Timestamp(day)
        still_open = []
        for pos in open_positions:
            if pos["exit_date"] == day:
                pnl_gross = pos["notional"] * pos["return_pct"] / 100.0
                cost = pos["notional"] * cost_rate
                cash += pos["notional"] + pnl_gross - cost
                completed.append({**pos, "gross_pnl": pnl_gross, "cost": cost,
                                  "net_pnl": pnl_gross - cost})
            else:
                still_open.append(pos)
        open_positions = still_open

        candidates = by_entry.get(day, [])
        for row in candidates:
            if len(open_positions) >= MAX_POSITIONS or cash + 1e-9 < POSITION_SIZE:
                break
            exit_date = pd.Timestamp(row[exit_col])
            if exit_date not in session_pos or session_pos[exit_date] <= session_pos[day]:
                continue
            if exit_date > pd.Timestamp(sessions[-1]):
                continue
            pos = {
                "Symbol": row["Symbol"], "signal_date": pd.Timestamp(row["Date"]),
                "entry_date": day, "exit_date": exit_date,
                "notional": min(POSITION_SIZE, cash),
                "return_pct": float(row[return_col]),
                "RVOL20": float(row["RVOL20"]),
            }
            cash -= pos["notional"]
            open_positions.append(pos)

    # The input cohort is restricted to complete outcomes, so any remaining
    # open position indicates malformed/missing session alignment and is not
    # silently marked to a fabricated price.
    if open_positions:
        raise ValueError(f"{len(open_positions)} positions remain open at sample end")
    equity = cash
    pnl = equity - CAPITAL
    trades = pd.DataFrame(completed)
    returns = trades["return_pct"] if not trades.empty else pd.Series(dtype=float)
    return {
        "Trades": int(len(trades)),
        "StartingCapitalINR": CAPITAL,
        "EndingEquityINR": round(equity, 2),
        "NetPnLINR": round(pnl, 2),
        "PortfolioReturnPct": round(pnl / CAPITAL * 100, 3),
        "TradeWinRatePct": round(float(returns.gt(0).mean() * 100), 2) if len(returns) else np.nan,
        "AverageTradeGrossReturnPct": round(float(returns.mean()), 3) if len(returns) else np.nan,
        "GrossProfitFactor": round(_pf(returns), 3) if len(returns) and math.isfinite(_pf(returns)) else (_pf(returns) if len(returns) else np.nan),
        "CostBpsRoundTrip": cost_bps,
        "OpenPositionsAtEnd": len(open_positions),
    }, trades


def run(signals_path=SIGNALS, sessions_path=SESSIONS, output_dir=OUT):
    output_dir.mkdir(parents=True, exist_ok=True)
    d = pd.read_csv(signals_path)
    sess = pd.read_csv(sessions_path)
    sessions = [pd.Timestamp(x).normalize() for x in sess["SessionDate"]]
    session_pos = {x: i for i, x in enumerate(sessions)}
    d["Date"] = pd.to_datetime(d["Date"]).dt.normalize()
    d["Symbol"] = d["Symbol"].astype(str).str.upper().str.strip()
    d["RVOL20"] = pd.to_numeric(d["RVOL20"], errors="coerce")
    d["AvgTradedValue20D_INR"] = pd.to_numeric(d["AvgTradedValue20D_INR"], errors="coerce")
    for h in HORIZONS:
        d[f"Return{h}D_Pct"] = pd.to_numeric(d[f"Return{h}D_Pct"], errors="coerce")
    complete = d[d["Return20D_Pct"].notna() & d["Date"].isin(session_pos)].copy()
    if complete.empty:
        raise ValueError("No complete 20-session outcomes; cannot form temporal folds.")
    start_idx = min(session_pos[x] for x in complete["Date"])
    end_idx = max(session_pos[x] for x in complete["Date"])
    folds = make_folds(sessions, start_idx, end_idx)
    if not folds:
        raise ValueError("Insufficient session history for train + 20-session embargo + test folds.")
    fold_rows, portfolio_rows, trade_rows = [], [], []
    for fold in folds:
        train_mask = complete["Date"].map(session_pos).between(fold["train_start_idx"], fold["train_end_idx"])
        test_mask = complete["Date"].map(session_pos).between(fold["test_start_idx"], fold["test_end_idx"])
        for strategy, selector in STRATEGIES.items():
            selected = selector(complete).fillna(False)
            train = non_overlapping(complete.loc[train_mask & selected], session_pos)
            test = non_overlapping(complete.loc[test_mask & selected], session_pos)
            for h in HORIZONS:
                train_m = outcome_metrics(train, h)
                test_m = outcome_metrics(test, h)
                fold_rows.append({
                    "Fold": fold["Fold"], "Strategy": strategy,
                    "TrainStart": fold["TrainStart"].date().isoformat(),
                    "TrainEnd": fold["TrainEnd"].date().isoformat(),
                    "EmbargoStart": fold["EmbargoStart"].date().isoformat(),
                    "EmbargoEnd": fold["EmbargoEnd"].date().isoformat(),
                    "TestStart": fold["TestStart"].date().isoformat(),
                    "TestEnd": fold["TestEnd"].date().isoformat(),
                    "HorizonSessions": h, "TrainSignals": len(train), "TestSignals": len(test),
                    **{f"Train{k}": v for k, v in train_m.items()},
                    **{f"Test{k}": v for k, v in test_m.items()},
                })
                # The portfolio simulation runs only on the test block. Signals
                # are ranked using signal-day RVOL, then liquidity, then symbol.
                for bps in COST_BPS:
                    p, trades = simulate_portfolio(test, sessions, h, bps)
                    portfolio_rows.append({
                        "Fold": fold["Fold"], "Strategy": strategy,
                        "HorizonSessions": h, **p,
                    })
                    if bps == 25 and not trades.empty:
                        trade_rows.extend([
                            {"Fold": fold["Fold"], "Strategy": strategy,
                             "HorizonSessions": h, **t}
                            for t in trades.to_dict("records")
                        ])
    pd.DataFrame(fold_rows).to_csv(output_dir / "walk_forward_metrics.csv", index=False)
    pd.DataFrame(portfolio_rows).to_csv(output_dir / "portfolio_sensitivity.csv", index=False)
    pd.DataFrame(trade_rows).to_csv(output_dir / "portfolio_trade_log_25bps.csv", index=False)
    pd.DataFrame([{
        "Status": "RESEARCH_ONLY_TEMPORAL_ROBUSTNESS_NOT_UNTOUCHED_OOS",
        "Reason": "Candidate rules were selected after reviewing the prior full-sample comparison; this chronological split is not a pristine holdout.",
        "SessionCount": len(sessions), "SignalDateStart": complete["Date"].min().date(),
        "SignalDateEnd20DComplete": complete["Date"].max().date(),
        "FoldCount": len(folds), "TrainSessionsPerFold": 20,
        "EmbargoSessionsPerFold": 20, "TestSessionsPerFold": 20,
        "CapitalINR": CAPITAL, "PositionSizeINR": POSITION_SIZE,
        "MaxPositions": MAX_POSITIONS,
        "CostSensitivity": "0, 25, 50 bps round trip; illustrative sensitivity, not broker-calculated charges",
        "Exit": "Horizon session close; no stop-loss or trailing exit; gross price outcomes from prior backtest",
        "Ranking": "Signal-day RVOL descending, prior-20-session traded value descending, symbol ascending",
        "ProductionChanged": False,
    }]).to_csv(output_dir / "validation_coverage.csv", index=False)
    print(pd.DataFrame(fold_rows).to_string(index=False))
    print(pd.DataFrame(portfolio_rows).to_string(index=False))
    print("[WALK FORWARD] Research-only; production scanner unchanged.")


if __name__ == "__main__":
    run()
