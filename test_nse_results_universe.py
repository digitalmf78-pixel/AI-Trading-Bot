from datetime import date

import pandas as pd
import pytest

import nse_results_universe as ru


class FakeResponse:
    def __init__(self, rows=None, status=200):
        self._rows = rows
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._rows


class FakeSession:
    def __init__(self, rows):
        self.rows = rows
        self.headers = {}

    def get(self, url, **kwargs):
        if url == ru.NSE_EVENT_PAGE:
            return FakeResponse([])
        return FakeResponse(self.rows)


def test_results_universe_uses_only_official_financial_results_and_next_90_days():
    rows = [
        {"symbol": "OLD", "date": "20-Oct-2026", "purpose": "Financial Results", "details": "Q2"},
        {"symbol": "NOW", "date": "25-Nov-2026", "purpose": "Financial Results", "details": "Q2"},
        {"symbol": "NEXT", "date": "15-Dec-2026", "purpose": "Financial Results/Other business matters", "details": "Q2"},
        {"symbol": "FAR", "date": "15-Jan-2027", "purpose": "Financial Results", "details": "Q3"},
        {"symbol": "OTHER", "date": "22-Nov-2026", "purpose": "Other business matters", "details": "No results"},
        {"symbol": "CANCEL", "date": "23-Nov-2026", "purpose": "Financial Results", "details": "Meeting cancelled"},
    ]
    source = FakeSession(rows)
    frame = pd.DataFrame({"TckrSymb": ["OLD", "NOW", "NEXT", "FAR", "OTHER", "CANCEL", "NO_DATE"]})

    filtered, audit, summary = ru.apply_official_results_universe_filter(
        frame, date(2026, 11, 18), session=source, lookahead_days=90
    )

    assert set(filtered["TckrSymb"]) == {"NOW", "NEXT", "FAR"}
    assert summary["last_month_companies"] == 1
    assert summary["this_month_companies"] == 1
    assert summary["next_month_companies"] == 1
    assert summary["results_universe_companies_90d"] == 3
    assert set(audit.loc[audit["ResultsUniverseStatus"].str.startswith("PASS"), "TckrSymb"]) == {"NOW", "NEXT", "FAR"}


def test_results_universe_does_not_include_unknown_symbols():
    source = FakeSession([
        {"symbol": "NOT_IN_MAINBOARD_FRAME", "date": "25-Nov-2026", "purpose": "Financial Results", "details": "Q2"}
    ])
    frame = pd.DataFrame({"TckrSymb": ["KNOWN"]})
    filtered, audit, summary = ru.apply_official_results_universe_filter(
        frame, date(2026, 11, 18), session=source
    )
    assert filtered.empty
    assert summary["results_universe_companies_90d"] == 0
    assert audit.iloc[0]["ResultsUniverseStatus"].startswith("EXCLUDED")


def test_empty_official_calendar_is_a_valid_zero_candidate_universe():
    source = FakeSession([])
    frame = pd.DataFrame({"TckrSymb": ["KNOWN"]})
    filtered, audit, summary = ru.apply_official_results_universe_filter(
        frame, date(2026, 11, 18), session=source
    )
    assert filtered.empty
    assert summary["results_universe_companies_90d"] == 0


def test_unavailable_official_source_fails_closed():
    class BrokenSession(FakeSession):
        def get(self, url, **kwargs):
            raise RuntimeError("network unavailable")

    with pytest.raises(ru.ResultsCalendarUnavailable, match="WAIT_FOR_DATA"):
        ru.collect_official_results_calendar(date(2026, 11, 18), session=BrokenSession([]))


def test_date_parser_handles_iso_and_nse_day_first_formats():
    assert ru._parse_date("2026-11-18") == date(2026, 11, 18)
    assert ru._parse_date("18-Nov-2026") == date(2026, 11, 18)
    assert ru._parse_date("not-a-date") is None
