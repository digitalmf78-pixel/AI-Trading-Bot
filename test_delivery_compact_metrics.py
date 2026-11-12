from datetime import date

import pandas as pd

import delivery_filter


def _session(day, value):
    return day, pd.DataFrame({"SYMBOL": ["AAA"], "SERIES": ["EQ"], "DELIV_PER": [value]})


def test_compact_delivery_counts_are_reporting_only_and_use_rolling_five_sessions(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(delivery_filter, "AUDIT_DIR", tmp_path / "outputs")
    candidates = pd.DataFrame([{"TckrSymb": "AAA", "SctySrs": "EQ"}])
    dates = [date(2026, 10, 1), date(2026, 10, 5), date(2026, 10, 6),
             date(2026, 10, 7), date(2026, 10, 8), date(2026, 10, 9), date(2026, 10, 12)]
    reports = [_session(day, value) for day, value in zip(dates, [50, 70, 70, 70, 70, 70, 70])]

    qualified, audit = delivery_filter.apply_delivery_filter(candidates, "2026-10-12", sessions=reports)
    row = audit.iloc[0]

    # Three five-session rolling averages ending within the 30-day window meet >=60%.
    assert row["DeliveryARolling5DPassCount30D"] == 3
    # Six individual sessions have Delivery >=60%.
    assert row["DeliveryDailyPassCount"] == 6
    assert row["DeliveryACount30DStatus"] == "FAIL"
    assert row["DeliveryBCount30DStatus"] == "PASS"
    # Existing production A/B eligibility remains based on the full-window average / every-day rule.
    assert row["DeliveryCategoryAStatus"] == "PASS_AVG_GE_60_PERCENT"
    assert row["DeliveryCategoryBStatus"] == "FILTERED_OUT_AT_LEAST_ONE_DAY_LT_60_PERCENT"
    assert qualified["TckrSymb"].tolist() == ["AAA"]
