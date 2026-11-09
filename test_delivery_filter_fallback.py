from datetime import date, timedelta

import pandas as pd

import delivery_filter
from nse_trading_calendar import is_trading_session


def _frame(symbol="AAA", values=(65.0,)):
    return pd.DataFrame({
        "SYMBOL": [symbol],
        "SERIES": ["EQ"],
        "DELIV_PER": list(values),
    })


def test_missing_asof_delivery_report_uses_latest_five_valid_sessions(monkeypatch, tmp_path):
    asof = date(2026, 10, 23)  # Friday; current report is not published yet.
    valid = {
        date(2026, 10, 22): _frame(values=(61.0,)),
        date(2026, 10, 21): _frame(values=(62.0,)),
        date(2026, 10, 15): _frame(values=(63.0,)),
        date(2026, 10, 19): _frame(values=(64.0,)),
        date(2026, 10, 16): _frame(values=(65.0,)),
    }

    def fake_read(_session, day):
        return valid.get(day)

    monkeypatch.setattr(delivery_filter, "_read_cached_or_download", fake_read)
    monkeypatch.setattr(delivery_filter, "CACHE_DIR", tmp_path / "cache")
    reports = delivery_filter.get_delivery_sessions(asof, required_sessions=5, max_calendar_days=10)

    dates = [day for day, _ in reports]
    assert len(dates) == 5
    assert len(set(dates)) == 5
    assert max(dates) == date(2026, 10, 22)
    assert asof not in dates


def test_delivery_audit_labels_actual_window_when_asof_report_missing(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(delivery_filter, "AUDIT_DIR", tmp_path / "outputs")
    candidates = pd.DataFrame([{"TckrSymb": "AAA", "SctySrs": "EQ"}])
    dates = [date(2026, 10, 15), date(2026, 10, 16), date(2026, 10, 19), date(2026, 10, 21), date(2026, 10, 22)]
    values = [55.0, 65.0, 58.0, 70.0, 62.0]  # average >= 60; not every day >= 60
    reports = [(day, _frame(values=(value,))) for day, value in zip(dates, values)]

    qualified, audit = delivery_filter.apply_delivery_filter(
        candidates, "2026-10-23", sessions=reports
    )

    row = audit.iloc[0]
    assert qualified["TckrSymb"].tolist() == ["AAA"]  # Category A alone qualifies (A OR B).
    assert row["DeliveryCategoryAStatus"] == "PASS_AVG_GE_60_PERCENT"
    assert row["DeliveryCategoryBStatus"] == "FILTERED_OUT_AT_LEAST_ONE_DAY_LT_60_PERCENT"
    assert row["DeliveryStatus"] == "PASS_GE_60_PERCENT"
    assert row["DeliveryFilterStatus"] == "PASS_GE_60_PERCENT"
    assert row["DeliveryAsOfDate"] == "2026-10-23"
    assert bool(row["DeliveryAsOfReportAvailable"]) is False
    assert row["DeliveryWindowStartDate"] == "2026-10-15"
    assert row["DeliveryWindowEndDate"] == "2026-10-22"
    assert row["LatestDeliveryPct"] == 62.0


def test_every_day_delivery_passes_downstream_gate(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(delivery_filter, "AUDIT_DIR", tmp_path / "outputs")
    candidates = pd.DataFrame([{"TckrSymb": "BBB", "SctySrs": "EQ"}])
    dates = [date(2026, 10, 16), date(2026, 10, 19), date(2026, 10, 20), date(2026, 10, 21), date(2026, 10, 22)]
    reports = [(day, _frame("BBB", (value,))) for day, value in zip(dates, [60, 65, 61, 70, 63])]
    qualified, audit = delivery_filter.apply_delivery_filter(candidates, "2026-10-23", sessions=reports)
    assert qualified["TckrSymb"].tolist() == ["BBB"]
    assert audit.iloc[0]["DeliveryCategoryAStatus"] == "PASS_AVG_GE_60_PERCENT"
    assert audit.iloc[0]["DeliveryCategoryBStatus"] == "PASS_EACH_DAY_GE_60_PERCENT"
    assert audit.iloc[0]["DeliveryFilterStatus"] == "PASS_GE_60_PERCENT"


def test_fewer_than_five_valid_reports_still_waits_for_data(monkeypatch, tmp_path):
    asof = date(2026, 10, 23)
    valid = {
        date(2026, 10, 22): _frame(values=(61.0,)),
        date(2026, 10, 21): _frame(values=(62.0,)),
    }
    monkeypatch.setattr(delivery_filter, "_read_cached_or_download", lambda _s, day: valid.get(day))
    monkeypatch.setattr(delivery_filter, "AUDIT_DIR", tmp_path / "outputs")
    candidates = pd.DataFrame([{"TckrSymb": "AAA", "SctySrs": "EQ"}])
    qualified, audit = delivery_filter.apply_delivery_filter(candidates, asof, http_session=None)
    assert qualified.empty
    assert audit.iloc[0]["DeliveryCategoryAStatus"] == "WAIT_FOR_DATA"
    assert audit.iloc[0]["DeliveryCategoryBStatus"] == "WAIT_FOR_DATA"



def test_30d_category_a_uses_average_of_all_valid_sessions_and_b_checks_each(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(delivery_filter, "AUDIT_DIR", tmp_path / "outputs")
    candidates = pd.DataFrame([{"TckrSymb": "AAA", "SctySrs": "EQ"}])
    dates = [date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 5),
             date(2026, 10, 6), date(2026, 10, 7), date(2026, 10, 8)]
    values = [50.0, 62.0, 62.0, 62.0, 62.0, 62.0]  # six-session mean is exactly 60
    reports = [(day, _frame("AAA", (value,))) for day, value in zip(dates, values)]
    _, audit = delivery_filter.apply_delivery_filter(candidates, "2026-10-08", sessions=reports)
    row = audit.iloc[0]
    assert row["DeliverySessions"] == 6
    assert row["AvgDelivery30D"] == 60.0
    assert row["DeliveryCategoryAStatus"] == "PASS_AVG_GE_60_PERCENT"
    assert row["DeliveryCategoryBStatus"] == "FILTERED_OUT_AT_LEAST_ONE_DAY_LT_60_PERCENT"


def test_30d_candidate_with_fewer_than_five_symbol_sessions_waits(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(delivery_filter, "AUDIT_DIR", tmp_path / "outputs")
    candidates = pd.DataFrame([{"TckrSymb": "AAA", "SctySrs": "EQ"}])
    dates = [date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 5),
             date(2026, 10, 6), date(2026, 10, 7), date(2026, 10, 8)]
    reports = [(day, _frame("AAA", (value,))) for day, value in zip(dates[:4], [61, 62, 63, 64])]
    reports += [(dates[4], pd.DataFrame(columns=["SYMBOL", "SERIES", "DELIV_PER"])),
                (dates[5], pd.DataFrame(columns=["SYMBOL", "SERIES", "DELIV_PER"]))]
    _, audit = delivery_filter.apply_delivery_filter(candidates, "2026-10-08", sessions=reports)
    assert audit.iloc[0]["DeliverySessions"] == 4
    assert audit.iloc[0]["DeliveryCategoryAStatus"] == "WAIT_FOR_DATA"
    assert audit.iloc[0]["DeliveryCategoryBStatus"] == "WAIT_FOR_DATA"


def test_collect_all_scans_complete_30d_window_and_returns_all_valid_reports(monkeypatch):
    asof = date(2026, 10, 30)
    valid_days = {asof - timedelta(days=offset) for offset in (0, 1, 2, 3, 4, 7, 8, 9)}
    calls = []
    def fake_read(_session, day):
        calls.append(day)
        return _frame() if day in valid_days else None
    monkeypatch.setattr(delivery_filter, "_read_cached_or_download", fake_read)
    reports = delivery_filter.get_delivery_sessions(
        asof, required_sessions=5, max_calendar_days=30, collect_all=True
    )
    expected = [day for day in valid_days if is_trading_session(day)]
    assert len(reports) == len(expected)
    assert len(calls) > 5
    assert len({day for day, _ in reports}) == len(reports)
