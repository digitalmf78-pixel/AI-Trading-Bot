from datetime import date
import pandas as pd

from delivery_categories import apply_delivery_categories


def _sessions(values_by_symbol):
    days = [date(2026, 10, 15), date(2026, 10, 16), date(2026, 10, 19),
            date(2026, 10, 21), date(2026, 10, 22), date(2026, 10, 23)]
    result = []
    for index, day in enumerate(days):
        rows = []
        for symbol, values in values_by_symbol.items():
            if values[index] is not None:
                rows.append({"SYMBOL": symbol, "SERIES": "EQ", "DELIV_PER": values[index]})
        result.append((day, pd.DataFrame(rows, columns=["SYMBOL", "SERIES", "DELIV_PER"])))
    return result


def test_30d_average_category_uses_all_six_valid_reports(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    candidates = pd.DataFrame([{"TckrSymb": "AAA", "SctySrs": "EQ"}])
    qualified, audit = apply_delivery_categories(
        candidates, "2026-10-23", sessions=_sessions({"AAA": [50, 62, 62, 62, 62, 62]})
    )
    assert len(qualified) == 1
    assert audit.iloc[0]["DeliverySessions"] == 6
    assert audit.iloc[0]["CategoryAStatus"] == "PASS"
    assert audit.iloc[0]["CategoryBStatus"] == "FAIL"
    assert audit.iloc[0]["AvgDelivery30D"] == 60
    assert (tmp_path / "outputs/v8_delivery_category_a_avg60.csv").exists()


def test_category_b_requires_every_valid_report_at_or_above_60(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    candidates = pd.DataFrame([{"TckrSymb": "BBB", "SctySrs": "EQ"}])
    qualified, audit = apply_delivery_categories(
        candidates, "2026-10-23", sessions=_sessions({"BBB": [60, 65, 61, 70, 63, 62]})
    )
    assert len(qualified) == 1
    assert audit.iloc[0]["CategoryAStatus"] == "PASS"
    assert audit.iloc[0]["CategoryBStatus"] == "PASS"


def test_average_below_60_fails_both_categories(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    candidates = pd.DataFrame([{"TckrSymb": "CCC", "SctySrs": "EQ"}])
    qualified, audit = apply_delivery_categories(
        candidates, "2026-10-23", sessions=_sessions({"CCC": [50, 55, 60, 62, 58, 59]})
    )
    assert qualified.empty
    assert audit.iloc[0]["CategoryAStatus"] == "FAIL"
    assert audit.iloc[0]["CategoryBStatus"] == "FAIL"


def test_candidate_with_fewer_than_five_valid_reports_waits(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    candidates = pd.DataFrame([{"TckrSymb": "DDD", "SctySrs": "EQ"}])
    qualified, audit = apply_delivery_categories(
        candidates, "2026-10-23",
        sessions=_sessions({"DDD": [60, None, None, None, 63, 70]}),
    )
    assert qualified.empty
    assert audit.iloc[0]["CategoryAStatus"] == "WAIT_FOR_DATA"
    assert audit.iloc[0]["CategoryBStatus"] == "WAIT_FOR_DATA"
