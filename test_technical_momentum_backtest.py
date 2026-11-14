import numpy as np
import pandas as pd

from technical_momentum_backtest import add_point_in_time_features


def _frame(n=260):
    close = np.linspace(100, 150, n)
    high = close * 1.01
    low = close * 0.99
    volume = np.full(n, 100000.0)
    traded = np.full(n, 25_000_000.0)
    return pd.DataFrame({
        "DATE": pd.date_range("2025-01-01", periods=n, freq="B"),
        "OPEN": close * 0.999, "HIGH": high, "LOW": low,
        "CLOSE": close, "VOLUME": volume, "TRADED_VALUE": traded,
    })


def test_features_are_point_in_time_and_require_warmup():
    source = _frame()
    source.loc[200, ["OPEN", "HIGH", "LOW", "CLOSE"]] = [159.0, 161.0, 158.0, 160.0]
    f = add_point_in_time_features(source)
    assert pd.isna(f.loc[198, "EMA200"])
    assert pd.notna(f.loc[199, "EMA200"])
    assert bool(f.loc[100, "FEATURES_MATURE"]) is True
    assert f.loc[200, "PRIOR20D_HIGH"] == f.loc[199, "HIGH"]
    assert bool(f.loc[200, "BREAKOUT_20D"]) is True


def test_vcp_dryup_uses_only_completed_prior_blocks_and_current_block():
    f = _frame()
    f.loc[200:219, "VOLUME"] = 100000
    f.loc[220:239, "VOLUME"] = 100000
    f.loc[240:259, "VOLUME"] = 40000
    out = add_point_in_time_features(f)
    assert out.loc[259, "VOLUME_RATIO_3_VS_2"] == 0.4
    assert bool(out.loc[259, "VCP_DRYUP_LT_0_5"]) is True


def test_empty_setup_still_returns_complete_zero_observation_metrics():
    from technical_momentum_backtest import _metric

    result = _metric(pd.DataFrame(), 5)
    assert result["OutcomeN_5D"] == 0
    assert pd.isna(result["WinRate_5D_Pct"])
    assert pd.isna(result["AverageReturn_5D_Pct"])
    assert pd.isna(result["MedianReturn_5D_Pct"])
    assert pd.isna(result["ProfitFactor_5D"])
    assert pd.isna(result["MFE_GE_15Pct_5D_Pct"])
