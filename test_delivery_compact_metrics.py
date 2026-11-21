from datetime import date

import pandas as pd

import delivery_filter


def _session(day, value):
    return day, pd.DataFrame({"SYMBOL": ["AAA"], "SERIES": ["EQ"], "DELIV_PER": [value]})


def test_compact_delivery_counts_are_reporting_only_and_use_consecutive_delivery_a(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(delivery_filter, "AUDIT_DIR", tmp_path / "outputs")
    candidates = pd.DataFrame([{"TckrSymb": "AAA", "SctySrs": "EQ"}])
    dates = [date(2026, 10, 1), date(2026, 10, 5), date(2026, 10, 6),
             date(2026, 10, 7), date(2026, 10, 8), date(2026, 10, 9), date(2026, 10, 12)]
    reports = [_session(day, value) for day, value in zip(dates, [50, 70, 70, 70, 70, 70, 70])]

    qualified, audit = delivery_filter.apply_delivery_filter(candidates, "2026-10-12", sessions=reports)
    row = audit.iloc[0]

    # Six consecutive daily observations meet the >=60% Delivery A rule.
    assert row["DeliveryARolling5DPassCount30D"] == 6
    # Six individual sessions have Delivery >=60%.
    assert row["DeliveryDailyPassCount"] == 6
    assert row["DeliveryACount30DStatus"] == "PASS"
    assert row["DeliveryBCount30DStatus"] == "PASS"
    # Production Category A uses the consecutive daily >=60% rule.
    assert row["DeliveryCategoryAStatus"] == "PASS_CONSECUTIVE_DAILY_DELIVERY_GE_60_AT_LEAST_5"
    assert row["DeliveryCategoryBStatus"] == "PASS_DAILY_DELIVERY_GE_60_AT_LEAST_5"
    assert qualified["TckrSymb"].tolist() == ["AAA"]
