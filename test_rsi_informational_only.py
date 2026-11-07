import pandas as pd

import volume_gainer
import news_catalyst


def test_rsi_observation_is_descriptive_only_for_all_zones():
    cases = [
        (25.0, 20.0, "OVERSOLD", "RISING", "OVERSOLD_RECOVERY"),
        (25.0, 30.0, "OVERSOLD", "FALLING", "OVERSOLD_PRESSURE"),
        (75.0, 80.0, "OVERBOUGHT", "FALLING", "OVERBOUGHT_COOLING"),
        (75.0, 70.0, "OVERBOUGHT", "RISING", "OVERBOUGHT_MOMENTUM"),
        (50.0, 49.0, "NEUTRAL", "RISING", "RSI_RISING"),
    ]
    for current, previous, zone, direction, behaviour in cases:
        result = volume_gainer.classify_rsi_observation(current, previous)
        assert result["RSIZone"] == zone
        assert result["RSIDirection"] == direction
        assert result["RSIBehaviour"] == behaviour
        assert result["RSIRetestStatus"] == "NOT_EVALUATED"
        assert result["RSIDivergenceStatus"] == "NOT_EVALUATED"


def test_missing_rsi_is_wait_for_data_not_a_rejection():
    result = volume_gainer.classify_rsi_observation(float("nan"), 40.0)
    assert result["RSIZone"] == "WAIT_FOR_DATA"
    assert result["RSIBehaviour"] == "WAIT_FOR_DATA"
    assert result["RSIRetestStatus"] == "NOT_EVALUATED"
    assert result["RSIDivergenceStatus"] == "NOT_EVALUATED"


def test_telegram_observation_rows_preserve_stock_even_when_rsi_missing():
    report = pd.DataFrame([{"TckrSymb": "ABC", "LiquidityTier": "TIER_1"}])
    downstream = pd.DataFrame([{
        "TckrSymb": "ABC", "RSI14": float("nan"),
        "RSIBehaviour": "WAIT_FOR_DATA", "EODWatchlistStatus": "WATCH",
    }])
    rows = news_catalyst._telegram_observation_rows(report, downstream)
    assert rows["TckrSymb"].tolist() == ["ABC"]


def test_telegram_rsi_display_contains_observation_and_no_rejection_wording():
    import inspect
    source = inspect.getsource(news_catalyst._observation_digest_lines)
    assert "RSI patterns: Retest" in source
    assert "informational only; no stock rejection" in source
