import math
import pandas as pd
from rvol_strategy_backtest import (classify_delivery, strategy_membership, _metric, delivery_window_dates, forward_session_dates)


def test_delivery_categories_use_all_valid_reports_and_minimum_five():
    assert classify_delivery([60, 60, 60, 60, 60]) == ("PASS", "PASS")
    assert classify_delivery([80, 80, 80, 80, 20]) == ("PASS", "REJECT")
    assert classify_delivery([80, 80, 80, 80, 20, 60]) == ("PASS", "REJECT")
    assert classify_delivery([59.99, 60, 60, 60, 60]) == ("REJECT", "REJECT")
    assert classify_delivery([60, 60, 60, 60]) == ("WAIT_FOR_DATA", "WAIT_FOR_DATA")


def test_delivery_window_is_inclusive_30_calendar_days():
    dates = pd.to_datetime(["2026-10-11", "2026-10-12", "2026-10-20", "2026-11-06", "2026-11-07"])
    got = delivery_window_dates(dates, "2026-11-06", max_calendar_days=30)
    assert [d.strftime("%Y-%m-%d") for d in got] == ["2026-10-12", "2026-10-20", "2026-11-06"]


def test_forward_horizons_use_next_market_sessions_and_require_full_horizon():
    dates = pd.to_datetime(["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06", "2026-11-09"])
    assert [d.strftime("%Y-%m-%d") for d in forward_session_dates(dates, "2026-11-02", 5)] == [
        "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06", "2026-11-09"
    ]
    assert forward_session_dates(dates, "2026-11-05", 5) == []


def test_rvol_strategy_boundaries():
    assert strategy_membership(1.50001) == (True, True, True)
    assert strategy_membership(1.5) == (False, True, True)
    assert strategy_membership(1.2) == (False, False, True)
    assert strategy_membership(0.8) == (False, False, True)
    assert strategy_membership(float("nan")) == (False, False, False)


def test_return_metrics_are_deterministic():
    result = _metric(pd.Series([10.0, -5.0, 0.0]), "R")
    assert result["RTrades"] == 3
    assert result["RWinRatePct"] == 33.33
    assert result["RAverageReturnPct"] == 1.667
    assert result["RMedianReturnPct"] == 0.0
    assert result["RProfitFactor"] == 2.0


def test_missing_cache_writes_wait_for_data_reports(tmp_path):
    from rvol_strategy_backtest import run_backtest

    result = run_backtest(
        price_dir=tmp_path / "missing_prices",
        delivery_dir=tmp_path / "missing_delivery",
        output_dir=tmp_path / "reports",
    )

    assert result["status"] == "WAIT_FOR_DATA"
    assert (tmp_path / "reports" / "comparison.csv").exists()
    assert (tmp_path / "reports" / "signals.csv").exists()
    rejection = pd.read_csv(tmp_path / "reports" / "rejection_counts.csv")
    assert rejection.iloc[0]["Status"] == "WAIT_FOR_DATA"
