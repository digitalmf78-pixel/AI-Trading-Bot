import math
import pandas as pd
from rvol_strategy_backtest import classify_delivery, strategy_membership, _metric


def test_delivery_categories_exactly_five_and_boundary():
    assert classify_delivery([60, 60, 60, 60, 60]) == ("PASS", "PASS")
    assert classify_delivery([80, 80, 80, 80, 20]) == ("PASS", "REJECT")
    assert classify_delivery([59.99, 60, 60, 60, 60]) == ("REJECT", "REJECT")
    assert classify_delivery([60, 60, 60, 60]) == ("WAIT_FOR_DATA", "WAIT_FOR_DATA")


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
