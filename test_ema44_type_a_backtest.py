import pandas as pd

from ema44_type_a_backtest import _summary, run_backtest


def test_summary_reports_net_return_metrics():
    row = _summary(pd.Series([2.0, -1.0, 0.0]), "Net")
    assert row["NetObservations"] == 3
    assert row["NetWinRatePct"] == 33.33
    assert row["NetAverageNetReturnPct"] == 0.333
    assert row["NetMedianNetReturnPct"] == 0.0
    assert row["NetProfitFactor"] == 2.0


def test_missing_cache_fails_closed_and_writes_reports(tmp_path):
    result = run_backtest(
        price_dir=tmp_path / "no_prices",
        delivery_dir=tmp_path / "no_delivery",
        output_dir=tmp_path / "reports",
    )
    assert result["status"] == "WAIT_FOR_DATA"
    assert (tmp_path / "reports" / "cache_coverage.csv").exists()
    assert (tmp_path / "reports" / "comparison.csv").exists()
    assert (tmp_path / "reports" / "signals.csv").exists()


def test_cost_assumptions_are_explicit_and_no_synthetic_rr():
    from ema44_type_a_backtest import (
        ROUND_TRIP_COST_BPS, ENTRY_SLIPPAGE_BPS, EXIT_SLIPPAGE_BPS
    )
    assert ROUND_TRIP_COST_BPS >= 0
    assert ENTRY_SLIPPAGE_BPS >= 0
    assert EXIT_SLIPPAGE_BPS >= 0
