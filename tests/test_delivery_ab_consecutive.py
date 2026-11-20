"""Regression tests for the approved NSE V8 Delivery A/B 30-calendar-day rules."""
from delivery_filter import _longest_consecutive_delivery_pass_count
from rvol_strategy_backtest import classify_delivery


def test_delivery_a_counts_longest_consecutive_60_percent_run():
    values = [61, 60, 72, 59, 90, 60, 61, 62, 63, 64, 40, 70]
    assert _longest_consecutive_delivery_pass_count(values) == 5
    assert classify_delivery(values) == ("PASS", "PASS")


def test_delivery_a_fails_when_five_qualifying_days_are_not_consecutive_but_b_passes():
    values = [60, 40, 60, 40, 60, 40, 60, 40, 60, 40]
    assert _longest_consecutive_delivery_pass_count(values) == 1
    assert classify_delivery(values) == ("REJECT", "PASS")


def test_delivery_a_and_b_both_pass_on_exactly_60_percent_for_five_consecutive_days():
    values = [55, 60, 60, 60, 60, 60, 55, 40]
    assert _longest_consecutive_delivery_pass_count(values) == 5
    assert classify_delivery(values) == ("PASS", "PASS")


def test_delivery_a_and_b_fail_below_five_qualifying_days():
    values = [60, 60, 59, 60, 59, 60, 55]
    assert _longest_consecutive_delivery_pass_count(values) == 2
    assert classify_delivery(values) == ("REJECT", "REJECT")


def test_delivery_classification_waits_when_fewer_than_five_valid_reports():
    assert classify_delivery([60, 61, 62, 63]) == ("WAIT_FOR_DATA", "WAIT_FOR_DATA")
