"""Opt-in live integration check for the official NSE event calendar.

Executed only by the dedicated PR workflow step; ordinary offline unit tests
remain deterministic and do not depend on NSE availability.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
import requests

from main_board_filter import HEADERS as MAINBOARD_HEADERS, NSE_MAIN_BOARD_URL, _symbols_from_csv
from nse_results_universe import collect_official_results_calendar


def test_live_nse_results_calendar_payload_and_mainboard_symbol_matching():
    as_of = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    try:
        calendar = collect_official_results_calendar(as_of)
    except Exception as exc:
        # NSE intermittently blocks hosted CI runners at the landing-page layer.
        # Skip only this external live check for an explicit HTTP 403; all
        # production code remains fail-closed and all offline contract tests run.
        if "403" in str(exc) and "nseindia.com" in str(exc).lower():
            pytest.skip(f"NSE denied this hosted CI runner (HTTP 403); production remains WAIT_FOR_DATA: {exc}")
        raise

    assert not calendar.empty, "Live NSE event calendar returned no Financial Results rows in the configured window"
    assert {"TckrSymb", "OfficialResultsDate", "ResultsPurpose"} <= set(calendar.columns)
    assert calendar["TckrSymb"].astype(str).str.strip().ne("").all()
    assert calendar["OfficialResultsDate"].astype(str).str.match(r"^\d{4}-\d{2}-\d{2}$").all()

    mainboard_session = requests.Session()
    mainboard_session.headers.update(MAINBOARD_HEADERS)
    response = mainboard_session.get(NSE_MAIN_BOARD_URL, timeout=(10, 30))
    try:
        response.raise_for_status()
    except requests.HTTPError:
        if response.status_code == 403:
            pytest.skip("NSE Mainboard CSV denied this hosted CI runner (HTTP 403); production validation is unchanged")
        raise
    mainboard_symbols = _symbols_from_csv(response.content)

    matched = sorted(set(calendar["TckrSymb"].astype(str).str.upper()) & mainboard_symbols)
    assert matched, "NSE calendar payload parsed, but no Financial Results symbol matched the official Mainboard list"
    print(
        f"LIVE_NSE_RESULTS_API_PASS as_of={as_of.isoformat()} "
        f"calendar_rows={len(calendar)} matched_mainboard_symbols={len(matched)} "
        f"sample={','.join(matched[:10])}"
    )
