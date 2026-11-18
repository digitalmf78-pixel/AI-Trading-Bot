"""Opt-in live integration check for the official NSE event calendar.

Executed only by the dedicated PR workflow step; ordinary offline unit tests
remain deterministic and do not depend on NSE availability.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from main_board_filter import HEADERS as MAINBOARD_HEADERS, NSE_MAIN_BOARD_URL, _symbols_from_csv
from nse_results_universe import collect_official_results_calendar


def test_live_nse_results_calendar_payload_and_mainboard_symbol_matching():
    as_of = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    calendar = collect_official_results_calendar(as_of)

    assert not calendar.empty, "Live NSE event calendar returned no Financial Results rows in the configured window"
    assert {"TckrSymb", "OfficialResultsDate", "ResultsPurpose"} <= set(calendar.columns)
    assert calendar["TckrSymb"].astype(str).str.strip().ne("").all()
    assert calendar["OfficialResultsDate"].astype(str).str.match(r"^\\d{4}-\\d{2}-\\d{2}$").all()

    mainboard_session = requests.Session()
    mainboard_session.headers.update(MAINBOARD_HEADERS)
    response = mainboard_session.get(NSE_MAIN_BOARD_URL, timeout=(10, 30))
    response.raise_for_status()
    mainboard_symbols = _symbols_from_csv(response.content)

    matched = sorted(set(calendar["TckrSymb"].astype(str).str.upper()) & mainboard_symbols)
    assert matched, "NSE calendar payload parsed, but no Financial Results symbol matched the official Mainboard list"
    print(
        f"LIVE_NSE_RESULTS_API_PASS as_of={as_of.isoformat()} "
        f"calendar_rows={len(calendar)} matched_mainboard_symbols={len(matched)} "
        f"sample={','.join(matched[:10])}"
    )
