"""Official NSE financial-results universe filter for NSE V8.

Only the input universe is narrowed. Existing Delivery A/B, liquidity, RVOL,
fundamental, news, sector, event, deal and technical stages remain unchanged.
No Bhavcopy or existing cache path is read, written, or modified here.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from pathlib import Path
import json
import re

import pandas as pd
import requests

NSE_EVENT_PAGE = "https://www.nseindia.com/companies-listing/corporate-filings-event-calendar"
NSE_EVENT_CALENDAR_URL = "https://www.nseindia.com/api/event-calendar"
NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": NSE_EVENT_PAGE,
}
RESULT_PATTERN = re.compile(r"financial\s*results?|quarterly\s*results?|audited\s+results?|unaudited\s+results?", re.I)
CANCEL_PATTERN = re.compile(r"cancelled|canceled|withdrawn|meeting stands cancelled", re.I)


class ResultsCalendarUnavailable(RuntimeError):
    """Raised when the official NSE results calendar cannot be verified."""


def _norm_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _pick(row: dict, *names: str) -> str:
    mapped = {_norm_key(key): value for key, value in row.items()}
    for name in names:
        value = mapped.get(_norm_key(name))
        if value is not None and str(value).strip().lower() not in {"", "nan", "none", "-"}:
            return str(value).strip()
    return ""


def _parse_date(value: object) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    dayfirst = not bool(re.match(r"^\d{4}-\d{2}-\d{2}$", raw))
    stamp = pd.to_datetime(raw, errors="coerce", dayfirst=dayfirst)
    if pd.isna(stamp):
        return None
    if stamp.tzinfo is not None:
        return stamp.tz_convert("Asia/Kolkata").date()
    return stamp.date()


def _payload_rows(response: requests.Response) -> list[dict]:
    try:
        payload = response.json()
    except (ValueError, json.JSONDecodeError):
        payload = None
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = next((payload.get(key) for key in ("data", "records", "result")
                     if isinstance(payload.get(key), list)), None)
        if rows is None:
            raise ValueError("NSE event calendar JSON has no recognized data array")
    else:
        raise ValueError("NSE event calendar returned non-JSON data")
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("NSE event calendar contains non-object rows")
    return rows


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, monthrange(year, month)[1])


def _month_shift(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def collect_official_results_calendar(as_of_date: date, session=None,
                                      lookahead_days: int = 90) -> pd.DataFrame:
    """Fetch NSE's official event calendar for previous month through +90 days.

    Only entries explicitly identified as Financial Results are accepted.
    A source failure or empty/invalid payload is not converted into an empty
    eligible universe: it raises WAIT_FOR_DATA to prevent a full-universe scan.
    """
    start_year, start_month = _month_shift(as_of_date.year, as_of_date.month, -1)
    window_start = date(start_year, start_month, 1)
    window_end = as_of_date + timedelta(days=int(lookahead_days))
    client = session or requests.Session()
    client.headers.update(NSE_HEADERS)
    try:
        landing = client.get(NSE_EVENT_PAGE, timeout=(5, 15))
        landing.raise_for_status()
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
        raw_rows = _payload_rows(response)
    except Exception as exc:
        raise ResultsCalendarUnavailable(
            f"WAIT_FOR_DATA: official NSE financial-results calendar unavailable: {type(exc).__name__}: {exc}"
        ) from exc

    rows = []
    for item in raw_rows:
        symbol = _pick(item, "symbol", "tradingSymbol", "SYMBOL", "BD_SYMBOL").upper()
        event_date = _parse_date(_pick(item, "date", "eventDate", "event_date", "meetingDate", "meeting_date"))
        purpose = _pick(item, "purpose", "eventType", "category")
        details = _pick(item, "details", "description", "subject")
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
                                           session=None, lookahead_days: int = 90):
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
    calendar = collect_official_results_calendar(as_of_date, session=session, lookahead_days=lookahead_days)
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
        "results_window_end": (as_of_date + timedelta(days=int(lookahead_days))).isoformat(),
        "last_month": f"{last_y:04d}-{last_m:02d}",
        "last_month_companies": int(calendar.loc[event_dates.between(last_start, last_end), "TckrSymb"].nunique()),
        "this_month": f"{as_of_date.year:04d}-{as_of_date.month:02d}",
        "this_month_companies": int(calendar.loc[event_dates.between(this_start, this_end), "TckrSymb"].nunique()),
        "next_month": f"{next_y:04d}-{next_m:02d}",
        "next_month_companies": int(calendar.loc[event_dates.between(next_start, next_end), "TckrSymb"].nunique()),
        "results_universe_companies_90d": int(calendar.loc[
            event_dates.between(as_of_date, as_of_date + timedelta(days=int(lookahead_days))),
            "TckrSymb"
        ].nunique()),
        "official_calendar_rows_matched_to_mainboard_bhavcopy": int(len(calendar)),
        "source": "NSE Official Event Calendar",
    }
    eligible = set(calendar.loc[
        event_dates.between(as_of_date, as_of_date + timedelta(days=int(lookahead_days))),
        "TckrSymb"
    ])
    filtered = frame.loc[symbols.isin(eligible)].copy()
    result_dates = (
        calendar.sort_values("OfficialResultsDate")
        .drop_duplicates("TckrSymb")
        .set_index("TckrSymb")["OfficialResultsDate"].to_dict()
    )
    audit = pd.DataFrame({
        "TckrSymb": symbols,
        "ResultsUniverseStatus": ["PASS_ANNOUNCED_WITHIN_90D" if s in eligible else "EXCLUDED_NO_CONFIRMED_RESULTS_WITHIN_90D" for s in symbols],
        "OfficialResultsDate": [result_dates.get(s, "") for s in symbols],
        "ResultsCalendarSource": "NSE_OFFICIAL_EVENT_CALENDAR",
    }).drop_duplicates("TckrSymb", keep="first").reset_index(drop=True)
    return filtered, audit, summary


def write_results_universe_reports(audit: pd.DataFrame, calendar: pd.DataFrame,
                                   summary: dict, eod_date: date) -> None:
    """Write diagnostics to outputs only; never writes to any cache directory."""
    output = Path("outputs")
    output.mkdir(parents=True, exist_ok=True)
    stamp = eod_date.strftime("%Y%m%d")
    audit.to_csv(output / f"v8_results_universe_audit_{stamp}.csv", index=False)
    calendar.to_csv(output / f"v8_official_results_calendar_{stamp}.csv", index=False)
    pd.DataFrame([summary]).to_csv(output / f"v8_results_universe_monthly_counts_{stamp}.csv", index=False)
    print(
        "[RESULTS UNIVERSE] "
        f"last_month={summary.get('last_month')}:{summary.get('last_month_companies', 0)} "
        f"this_month={summary.get('this_month')}:{summary.get('this_month_companies', 0)} "
        f"next_month={summary.get('next_month')}:{summary.get('next_month_companies', 0)} "
        f"eligible_next_90d={summary.get('results_universe_companies_90d', 0)}"
    )
