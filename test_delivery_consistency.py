import pandas as pd

from delivery_consistency import build_delivery_consistency_report


def _sessions(values_by_symbol, start="2026-10-01"):
    dates = pd.bdate_range(start=start, periods=20)
    reports = []
    for index, day in enumerate(dates):
        rows = []
        for symbol, values in values_by_symbol.items():
            value = values[index]
            if value is not None:
                rows.append({"SYMBOL": symbol, "SERIES": "EQ", "DELIV_PER": value})
        reports.append((day.date(), pd.DataFrame(rows, columns=["SYMBOL", "SERIES", "DELIV_PER"])))
    return reports


def test_all_twenty_days_at_or_above_sixty_gets_very_high_tag():
    candidates = pd.DataFrame([{"TckrSymb": "AAA", "SctySrs": "EQ"}])
    enriched, report = build_delivery_consistency_report(
        candidates, "2026-10-28", sessions=_sessions({"AAA": [60.0] * 20})
    )
    row = enriched.iloc[0]
    assert row["Delivery5DCategoryAStatus"] == "PASS_AVG_GE_60_PERCENT"
    assert row["Delivery5DCategoryBStatus"] == "PASS_EACH_DAY_GE_60_PERCENT"
    assert row["Delivery10DCategoryAStatus"] == "PASS_AVG_GE_60_PERCENT"
    assert row["Delivery10DCategoryBStatus"] == "PASS_EACH_DAY_GE_60_PERCENT"
    assert row["Delivery20DCategoryAStatus"] == "PASS_AVG_GE_60_PERCENT"
    assert row["Delivery20DCategoryBStatus"] == "PASS_EACH_DAY_GE_60_PERCENT"
    assert row["Delivery20DTag"] == "VERY_HIGH_CONSISTENCY"
    assert row["Delivery20DCurrentStreak"] == 20
    assert len(report) == 1


def test_twenty_day_average_category_a_can_pass_while_b_fails():
    values = [61.0] * 19 + [59.0]
    candidates = pd.DataFrame([{"TckrSymb": "AAA", "SctySrs": "EQ"}])
    enriched, _ = build_delivery_consistency_report(
        candidates, "2026-10-28", sessions=_sessions({"AAA": values})
    )
    row = enriched.iloc[0]
    assert row["Delivery20DCategoryAStatus"] == "PASS_AVG_GE_60_PERCENT"
    assert row["Delivery20DCategoryBStatus"] == "FAIL_AT_LEAST_ONE_DAY_LT_60_PERCENT"
    assert row["Delivery20DDailyPassCount"] == 19
    assert row["Delivery20DTag"] == "HIGH_CONSISTENCY"
    assert row["Delivery20DCurrentStreak"] == 0


def test_missing_symbol_session_fails_closed_without_rejecting_candidate():
    values = [65.0] * 20
    values[12] = None
    candidates = pd.DataFrame([{"TckrSymb": "AAA", "SctySrs": "EQ"}])
    enriched, _ = build_delivery_consistency_report(
        candidates, "2026-10-28", sessions=_sessions({"AAA": values})
    )
    row = enriched.iloc[0]
    assert row["Delivery20DSessions"] == 19
    assert row["Delivery20DCategoryAStatus"] == "WAIT_FOR_DATA"
    assert row["Delivery20DCategoryBStatus"] == "WAIT_FOR_DATA"
    assert row["Delivery20DTag"] == "WAIT_FOR_DATA"
    assert len(enriched) == 1


def test_threshold_is_inclusive_at_exactly_sixty():
    candidates = pd.DataFrame([{"TckrSymb": "AAA", "SctySrs": "EQ"}])
    enriched, _ = build_delivery_consistency_report(
        candidates, "2026-10-28", sessions=_sessions({"AAA": [60.0] * 20})
    )
    assert enriched.iloc[0]["Delivery20DCategoryAStatus"] == "PASS_AVG_GE_60_PERCENT"
    assert enriched.iloc[0]["Delivery20DCategoryBStatus"] == "PASS_EACH_DAY_GE_60_PERCENT"
