"""Official NSE financial-results universe filter for NSE V8.

Only the input universe is narrowed. Existing Delivery A/B, liquidity, RVOL,
fundamental, news, sector, event, deal and technical stages remain unchanged.
No Bhavcopy or existing cache path is read, written, or modified here.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from pathlib import Path
import re

import pandas as pd
from strategies.ecms.information import (
    NSE_EVENT_CALENDAR_URL,
    NSE_EVENT_PAGE,
    _as_date as _parse_date,
    _nse_session,
    _payload_rows as _nse_payload_rows,
    _pick as _nse_pick,
)
RESULT_PATTERN = re.compile(r"financial\s*results?|quarterly\s*results?|audited\s+results?|unaudited\s+results?", re.I)
CANCEL_PATTERN = re.compile(r"cancelled|canceled|withdrawn|meeting stands cancelled", re.I)


class ResultsCalendarUnavailable(RuntimeError):
    """Raised when the official NSE results calendar cannot be verified."""


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, monthrange(year, month)[1])


def _month_shift(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def _add_months(day: date, months: int) -> date:
    """Calendar-month arithmetic with end-of-month clamping."""
    year, month = _month_shift(day.year, day.month, months)
    return date(year, month, min(day.day, monthrange(year, month)[1]))


def collect_official_results_calendar(as_of_date: date, session=None,
                                      lookahead_months: int = 3) -> pd.DataFrame:
    """Fetch NSE's official event calendar from previous-month start through +3 calendar months.

    Only entries explicitly identified as Financial Results are accepted.
    A source failure or invalid payload raises WAIT_FOR_DATA to prevent a
    silent fallback to the full Mainboard universe.
    """
    start_year, start_month = _month_shift(as_of_date.year, as_of_date.month, -1)
    window_start = date(start_year, start_month, 1)
    window_end = _add_months(as_of_date, int(lookahead_months))
    try:
        # Reuse the production NSE cookie/session and payload parser from
        # strategies/ecms/information.py instead of maintaining duplicate
        # headers, cookies, and response-shape assumptions.
        client = _nse_session(session, NSE_EVENT_PAGE)
        response = client.get(
            NSE_EVENT_CALENDAR_URL,
            params={
                "index": "equities",
                "from_date": window_start.strftime("%d-%m-%Y"),
                "to_date": window_end.strftime("%d-%m-%Y"),
            },
            timeout=(5, 25),
        )
        response.raise_for_status()
        raw_rows = _nse_payload_rows(response)
    except Exception as exc:
        raise ResultsCalendarUnavailable(
            f"WAIT_FOR_DATA: official NSE financial-results calendar unavailable: {type(exc).__name__}: {exc}"
        ) from exc

    rows = []
    schema_rows = 0
    for item in raw_rows:
        symbol = str(_nse_pick(item, "symbol", "tradingSymbol", "SYMBOL", "BD_SYMBOL")).strip().upper()
        event_date_raw = _nse_pick(item, "date", "eventDate", "event_date", "meetingDate", "meeting_date")
        purpose = str(_nse_pick(item, "purpose", "eventType", "category")).strip()
        details = str(_nse_pick(item, "details", "description", "subject")).strip()
        if symbol and event_date_raw and purpose:
            schema_rows += 1
        event_date = _parse_date(event_date_raw)
        combined = f"{purpose} {details}".strip()
        if not symbol or event_date is None or not (window_start <= event_date <= window_end):
            continue
        if not RESULT_PATTERN.search(combined) or CANCEL_PATTERN.search(combined):
            continue
        rows.append({
            "TckrSymb": symbol,
            "OfficialResultsDate": event_date.isoformat(),
            "ResultsPurpose": purpose,
            "ResultsDetails": details,
            "ResultsSource": "NSE Official Event Calendar",
            "ResultsSourceType": "OFFICIAL",
            "ResultsSourceURL": NSE_EVENT_PAGE,
            "ResultsCalendarAsOf": as_of_date.isoformat(),
        })

    if raw_rows and schema_rows == 0:
        raise ResultsCalendarUnavailable(
            "WAIT_FOR_DATA: NSE event calendar payload schema changed; "
            "no rows exposed recognized symbol/date/purpose fields"
        )

    frame = pd.DataFrame(rows, columns=[
        "TckrSymb", "OfficialResultsDate", "ResultsPurpose", "ResultsDetails",
        "ResultsSource", "ResultsSourceType", "ResultsSourceURL", "ResultsCalendarAsOf",
    ])
    frame = frame.drop_duplicates(
        subset=["TckrSymb", "OfficialResultsDate", "ResultsPurpose", "ResultsDetails"],
        keep="last",
    ).sort_values(["OfficialResultsDate", "TckrSymb"]).reset_index(drop=True)
    return frame


def apply_official_results_universe_filter(frame: pd.DataFrame, as_of_date: date,
                                           session=None, lookahead_months: int = 3):
    """Intersect the current official Mainboard/Bhavcopy cohort with announced results.

    The returned candidate frame is the only changed input to the existing V8
    pipeline. All downstream filters and their order are left to volume_gainer.py.
    """
    if frame is None or frame.empty:
        empty = frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()
        return empty, pd.DataFrame(), {
            "last_month_companies": 0, "this_month_companies": 0,
            "next_month_companies": 0, "results_universe_companies_90d": 0,
        }
    if "TckrSymb" not in frame.columns:
        raise ValueError("Results universe filter requires TckrSymb")
    calendar = collect_official_results_calendar(as_of_date, session=session, lookahead_months=lookahead_months)
    symbols = frame["TckrSymb"].astype(str).str.strip().str.upper()
    mainboard_symbols = set(symbols[symbols.ne("")])
    calendar = calendar[calendar["TckrSymb"].isin(mainboard_symbols)].copy()

    last_y, last_m = _month_shift(as_of_date.year, as_of_date.month, -1)
    next_y, next_m = _month_shift(as_of_date.year, as_of_date.month, 1)
    last_start, last_end = _month_bounds(last_y, last_m)
    this_start, this_end = _month_bounds(as_of_date.year, as_of_date.month)
    next_start, next_end = _month_bounds(next_y, next_m)
    event_dates = pd.to_datetime(calendar["OfficialResultsDate"], errors="coerce").dt.date
    summary = {
        "as_of_date": as_of_date.isoformat(),
        "results_window_end": _add_months(as_of_date, int(lookahead_months)).isoformat(),
        "last_month": f"{last_y:04d}-{last_m:02d}",
        "last_month_companies": int(calendar.loc[event_dates.between(last_start, last_end), "TckrSymb"].nunique()),
        "this_month": f"{as_of_date.year:04d}-{as_of_date.month:02d}",
        "this_month_companies": int(calendar.loc[event_dates.between(this_start, this_end), "TckrSymb"].nunique()),
        "next_month": f"{next_y:04d}-{next_m:02d}",
        "next_month_companies": int(calendar.loc[event_dates.between(next_start, next_end), "TckrSymb"].nunique()),
        "official_calendar_rows_matched_to_mainboard_bhavcopy": int(len(calendar)),
        "source": "NSE Official Event Calendar",
    }
    p1_end = _add_months(as_of_date, 1)
    p2_end = _add_months(as_of_date, 2)
    p3_end = _add_months(as_of_date, int(lookahead_months))
    # Include the immediately preceding calendar month for post-announcement verification.
    # Those rows are not eligible until the exact financial period is confirmed by NSE filing.
    in_window = event_dates.between(last_start, p3_end)
    future_calendar = calendar.loc[in_window].copy()
    future_dates = pd.to_datetime(future_calendar["OfficialResultsDate"], errors="coerce").dt.date
    future_calendar["ResultsPriority"] = [
        "P0_LAST_MONTH_REQUIRES_VERIFIED_FILING" if d < as_of_date else
        "P1_WITHIN_1_MONTH" if d <= p1_end else
        "P2_WITHIN_2_MONTHS" if d <= p2_end else
        "P3_WITHIN_3_MONTHS"
        for d in future_dates
    ]
    priority_rank = {"P0_LAST_MONTH_REQUIRES_VERIFIED_FILING": 0, "P1_WITHIN_1_MONTH": 1, "P2_WITHIN_2_MONTHS": 2, "P3_WITHIN_3_MONTHS": 3}
    future_calendar["ResultsPriorityRank"] = future_calendar["ResultsPriority"].map(priority_rank)
    summary.update({
        "priority_p1_window_end": p1_end.isoformat(),
        "priority_p1_companies": int(future_calendar.loc[future_calendar["ResultsPriority"].eq("P1_WITHIN_1_MONTH"), "TckrSymb"].nunique()),
        "priority_p2_window_end": p2_end.isoformat(),
        "priority_p2_companies": int(future_calendar.loc[future_calendar["ResultsPriority"].eq("P2_WITHIN_2_MONTHS"), "TckrSymb"].nunique()),
        "priority_p3_window_end": p3_end.isoformat(),
        "priority_p3_companies": int(future_calendar.loc[future_calendar["ResultsPriority"].eq("P3_WITHIN_3_MONTHS"), "TckrSymb"].nunique()),
        "results_universe_companies_3m": int(future_calendar["TckrSymb"].nunique()),
        "last_month_results_candidates_requiring_filing": int(future_calendar.loc[future_calendar["ResultsPriority"].eq("P0_LAST_MONTH_REQUIRES_VERIFIED_FILING"), "TckrSymb"].nunique()),
    })
    eligible = set(future_calendar["TckrSymb"])
    filtered = frame.loc[symbols.isin(eligible)].copy()
    result_dates = (
        future_calendar.sort_values(["OfficialResultsDate", "TckrSymb"])
        .drop_duplicates("TckrSymb")
        .set_index("TckrSymb")["OfficialResultsDate"].to_dict()
    )
    result_priority = (
        future_calendar.sort_values(["OfficialResultsDate", "TckrSymb"])
        .drop_duplicates("TckrSymb")
        .set_index("TckrSymb")["ResultsPriority"].to_dict()
    )
    result_priority_rank = {symbol: priority_rank[label] for symbol, label in result_priority.items()}
    filtered["OfficialResultsDate"] = filtered["TckrSymb"].astype(str).str.strip().str.upper().map(result_dates)
    filtered["ResultsPriority"] = filtered["TckrSymb"].astype(str).str.strip().str.upper().map(result_priority)
    filtered["ResultsPriorityRank"] = filtered["TckrSymb"].astype(str).str.strip().str.upper().map(result_priority_rank)
    filtered = filtered.sort_values(["ResultsPriorityRank", "OfficialResultsDate", "TckrSymb"], kind="stable").reset_index(drop=True)
    event_meta = (
        future_calendar.sort_values(["OfficialResultsDate", "TckrSymb"])
        .drop_duplicates("TckrSymb")
        .set_index("TckrSymb")
        .to_dict("index")
    )
    audit = pd.DataFrame({
        "TckrSymb": symbols,
        "ResultsUniverseStatus": ["PASS_ANNOUNCED_WITHIN_3M" if s in eligible else "EXCLUDED_NO_CONFIRMED_RESULTS_WITHIN_3M" for s in symbols],
        "OfficialResultsDate": [result_dates.get(s, "") for s in symbols],
        "ResultsPriority": [result_priority.get(s, "") for s in symbols],
        "ResultsPriorityRank": [result_priority_rank.get(s, "") for s in symbols],
        "ResultsPurpose": [event_meta.get(s, {}).get("ResultsPurpose", "") for s in symbols],
        "ResultsDetails": [event_meta.get(s, {}).get("ResultsDetails", "") for s in symbols],
        "ResultsSourceURL": [event_meta.get(s, {}).get("ResultsSourceURL", "") for s in symbols],
        "ResultsCalendarAsOf": as_of_date.isoformat(),
        "ResultsCalendarSource": "NSE_OFFICIAL_EVENT_CALENDAR",
    }).drop_duplicates("TckrSymb", keep="first").reset_index(drop=True)
    return filtered, audit, summary


def write_results_universe_reports(audit: pd.DataFrame, summary: dict, eod_date: date) -> None:
    """Write diagnostics to outputs only; never writes to any cache directory."""
    output = Path("outputs")
    output.mkdir(parents=True, exist_ok=True)
    stamp = eod_date.strftime("%Y%m%d")
    audit.to_csv(output / f"v8_results_universe_audit_{stamp}.csv", index=False)
    pd.DataFrame([summary]).to_csv(output / f"v8_results_universe_monthly_counts_{stamp}.csv", index=False)
    print(
        "[RESULTS UNIVERSE] "
        f"last_month={summary.get('last_month')}:{summary.get('last_month_companies', 0)} "
        f"this_month={summary.get('this_month')}:{summary.get('this_month_companies', 0)} "
        f"next_month={summary.get('next_month')}:{summary.get('next_month_companies', 0)} "
        f"P1_1m={summary.get('priority_p1_companies', 0)} "
        f"P2_2m={summary.get('priority_p2_companies', 0)} "
        f"P3_3m={summary.get('priority_p3_companies', 0)} "
        f"eligible_next_3m={summary.get('results_universe_companies_3m', 0)}"
    )
