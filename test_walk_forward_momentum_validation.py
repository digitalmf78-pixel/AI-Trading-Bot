import pandas as pd
from walk_forward_momentum_validation import make_folds, simulate_portfolio


def test_make_folds_has_purged_gap():
    sessions = list(pd.date_range("2026-01-01", periods=100, freq="B"))
    folds = make_folds(sessions, 0, 99, train_len=20, embargo=20, test_len=20)
    assert len(folds) == 2
    assert folds[0]["test_start_idx"] - folds[0]["train_end_idx"] == 21
    assert folds[1]["test_start_idx"] - folds[1]["train_end_idx"] == 21


def test_portfolio_respects_four_slots_and_costs():
    sessions = list(pd.date_range("2026-01-01", periods=12, freq="B"))
    rows = []
    for i, symbol in enumerate(["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]):
        rows.append({
            "Symbol": symbol, "Date": sessions[0],
            "EntryDate5D": sessions[1], "OutcomeEndDate5D": sessions[6],
            "Return5D_Pct": 10.0, "RVOL20": 2.0 - i * 0.1,
            "AvgTradedValue20D_INR": 30_000_000,
        })
    result, trades = simulate_portfolio(pd.DataFrame(rows), sessions, 5, 25)
    assert result["Trades"] == 4
    assert result["OpenPositionsAtEnd"] == 0
    assert result["NetPnLINR"] < 10_000
    assert set(trades["Symbol"]).issubset({"AAA", "BBB", "CCC", "DDD"})
