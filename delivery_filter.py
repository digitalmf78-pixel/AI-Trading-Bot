"""NSE EOD five-session delivery-first shortlist filter.

Rule: average Delivery % across the latest EOD session plus the previous four
available NSE trading-session reports must be greater than or equal to 60% to qualify.
Missing/invalid reports or fewer than five distinct sessions never PASS.
"""
from __future__ import annotations

import io
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests

BASE_URL = "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{date}.csv"
CACHE_DIR = Path("data/cache/delivery")
AUDIT_DIR = Path("data/reports")
MINIMUM_AVERAGE = 60.0
REQUIRED_COLUMNS = {"SYMBOL", "SERIES", "DELIV_PER"}
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept": "text/csv,text/plain,*/*",
    "Referer": "https://www.nseindia.com/",
}


def _normalise_columns(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame.columns = [str(c).strip().upper().replace(" ", "_") for c in frame.columns]
    return frame


def _parse_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return pd.Timestamp(value).date()


def _read_cached_or_download(session: requests.Session, session_date: date) -> pd.DataFrame | None:
    date_token = session_date.strftime("%d%m%Y")
    cache_path = CACHE_DIR / f"sec_bhavdata_full_{date_token}.csv"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if cache_path.exists() and cache_path.stat().st_size > 1000:
        try:
            frame = _normalise_columns(pd.read_csv(cache_path))
            if REQUIRED_COLUMNS.issubset(frame.columns) and not frame.empty:
                return frame
        except Exception:
            # A corrupt cache is not treated as valid data; attempt a fresh download.
            pass

    url = BASE_URL.format(date=date_token)
    try:
        response = session.get(url, timeout=25)
    except requests.RequestException as exc:
        print(f"[DELIVERY] Download error {session_date}: {exc}")
        return None

    if response.status_code != 200:
        print(f"[DELIVERY] Report unavailable {session_date}: HTTP {response.status_code}")
        return None
    content = response.content
    if not content or content.lstrip().lower().startswith((b"<html", b"<!doctype")):
        print(f"[DELIVERY] Invalid/HTML report for {session_date}")
        return None
    try:
        frame = _normalise_columns(pd.read_csv(io.BytesIO(content)))
    except Exception as exc:
        print(f"[DELIVERY] CSV parse error {session_date}: {exc}")
        return None
    if not REQUIRED_COLUMNS.issubset(frame.columns) or frame.empty:
        print(f"[DELIVERY] Required columns/data missing for {session_date}")
        return None
    cache_path.write_bytes(content)
    return frame


def get_delivery_sessions(asof_date, required_sessions: int = 5, max_calendar_days: int = 35,
                          session: requests.Session | None = None) -> list[tuple[date, pd.DataFrame]]:
    """Return latest `required_sessions` distinct valid reports, including asof_date."""
    asof = _parse_date(asof_date)
    http = session or requests.Session()
    http.headers.update(HEADERS)
    found: list[tuple[date, pd.DataFrame]] = []
    seen: set[date] = set()
    for offset in range(max_calendar_days + 1):
        day = asof - timedelta(days=offset)
        # Weekends are skipped; official report availability also handles exchange holidays.
        if day.weekday() >= 5:
            continue
        frame = _read_cached_or_download(http, day)
        if frame is None:
            # The requested as-of session must be present: silently replacing it
            # with an older report would violate the user's current-day rule.
            if offset == 0:
                raise RuntimeError(
                    f"WAIT_FOR_DATA: current EOD delivery report for {asof.isoformat()} is unavailable; "
                    "cannot substitute an older session"
                )
            continue
        if day in seen:
            continue
        frame = frame.copy()
        frame["REPORT_DATE"] = day.isoformat()
        found.append((day, frame))
        seen.add(day)
        print(f"[DELIVERY] Accepted report {day}: {len(frame)} rows ({len(found)}/{required_sessions})")
        if len(found) >= required_sessions:
            return found
    raise RuntimeError(
        f"WAIT_FOR_DATA: only {len(found)}/{required_sessions} distinct delivery reports "
        f"found by {asof.isoformat()} within {max_calendar_days} calendar days"
    )


def apply_delivery_filter(candidates: pd.DataFrame, asof_date, symbol_col: str = "TckrSymb",
                          series_col: str = "SctySrs", minimum_average: float = MINIMUM_AVERAGE,
                          sessions: list[tuple[date, pd.DataFrame]] | None = None,
                          http_session: requests.Session | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return qualifying candidates and full per-symbol audit.

    Qualifies only if five distinct valid reports have a valid delivery percentage
    for the exact SYMBOL+SERIES and their arithmetic mean is greater than or equal to threshold.
    """
    if candidates.empty:
        return candidates.copy(), pd.DataFrame()
    if symbol_col not in candidates.columns:
        raise ValueError(f"Candidate symbol column missing: {symbol_col}")

    try:
        reports = sessions if sessions is not None else get_delivery_sessions(asof_date, 5, session=http_session)
        if len({day for day, _ in reports}) < 5:
            raise RuntimeError("WAIT_FOR_DATA: fewer than five distinct delivery sessions")
    except RuntimeError as exc:
        if "WAIT_FOR_DATA" not in str(exc):
            raise
        print(f"[DELIVERY] {exc}")
        audit = candidates.copy()
        audit["DeliverySessions"] = 0
        audit["AvgDelivery5D"] = float("nan")
        audit["LatestDeliveryPct"] = float("nan")
        audit["DeliveryStatus"] = "WAIT_FOR_DATA"
        audit["DeliveryFilterStatus"] = "WAIT_FOR_DATA"
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        audit_path = AUDIT_DIR / f"delivery_first_audit_{_parse_date(asof_date).strftime('%Y%m%d')}.csv"
        audit.to_csv(audit_path, index=False)
        print("[DELIVERY] No candidates allowed through because required data is missing.")
        print(f"[DELIVERY] WAIT_FOR_DATA audit saved: {audit_path}")
        return candidates.iloc[0:0].copy(), audit

    pieces = []
    for report_date, raw in reports:
        frame = _normalise_columns(raw)
        if not REQUIRED_COLUMNS.issubset(frame.columns):
            raise RuntimeError(f"WAIT_FOR_DATA: delivery columns missing for {report_date}")
        frame = frame[["SYMBOL", "SERIES", "DELIV_PER"]].copy()
        frame["SYMBOL"] = frame["SYMBOL"].astype(str).str.strip().str.upper()
        frame["SERIES"] = frame["SERIES"].astype(str).str.strip().str.upper()
        frame["DELIV_PER"] = pd.to_numeric(frame["DELIV_PER"], errors="coerce")
        frame = frame[frame["DELIV_PER"].between(0, 100, inclusive="both")]
        frame["REPORT_DATE"] = report_date.isoformat()
        # A duplicate symbol/series/date row must not inflate the five-session count.
        frame = frame.drop_duplicates(["SYMBOL", "SERIES", "REPORT_DATE"], keep="last")
        pieces.append(frame)

    all_delivery = pd.concat(pieces, ignore_index=True)
    candidate = candidates.copy()
    candidate["_SYMBOL_KEY"] = candidate[symbol_col].astype(str).str.strip().str.upper()
    if series_col in candidate.columns:
        candidate["_SERIES_KEY"] = candidate[series_col].astype(str).str.strip().str.upper()
    else:
        candidate["_SERIES_KEY"] = "EQ"

    audits = []
    for _, row in candidate.iterrows():
        sym, ser = row["_SYMBOL_KEY"], row["_SERIES_KEY"]
        matches = all_delivery[(all_delivery["SYMBOL"] == sym) & (all_delivery["SERIES"] == ser)]
        distinct = matches.drop_duplicates("REPORT_DATE")
        count = int(distinct["REPORT_DATE"].nunique())
        avg = float(distinct["DELIV_PER"].mean()) if count == 5 else float("nan")
        by_date = {r["REPORT_DATE"]: float(r["DELIV_PER"]) for _, r in distinct.iterrows()}
        record = row.drop(labels=["_SYMBOL_KEY", "_SERIES_KEY"]).to_dict()
        record.update({
            "DeliverySessions": count,
            "AvgDelivery5D": avg,
            "LatestDeliveryPct": by_date.get(_parse_date(asof_date).isoformat(), float("nan")),
            "DeliveryStatus": "WAIT_FOR_DATA" if count != 5 else ("PASS_GE_60_PERCENT" if avg >= minimum_average else "FILTERED_OUT_LT_60_PERCENT"),
            "DeliveryFilterStatus": "WAIT_FOR_DATA" if count != 5 else ("PASS_GE_60_PERCENT" if avg >= minimum_average else "FILTERED_OUT_LT_60_PERCENT"),
        })
        for i, (report_date, _) in enumerate(reports, start=1):
            record[f"Delivery_{report_date.isoformat()}"] = by_date.get(report_date.isoformat(), float("nan"))
        audits.append(record)

    audit = pd.DataFrame(audits)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    audit_path = AUDIT_DIR / f"delivery_first_audit_{_parse_date(asof_date).strftime('%Y%m%d')}.csv"
    audit.to_csv(audit_path, index=False)
    qualified = audit[audit["DeliveryStatus"] == "PASS_GE_60_PERCENT"].copy()
    print(f"[DELIVERY] Candidates checked: {len(audit)}")
    print(f"[DELIVERY] Qualified (>={minimum_average:.1f}%): {len(qualified)}")
    print(f"[DELIVERY] WAIT_FOR_DATA: {(audit['DeliveryStatus'] == 'WAIT_FOR_DATA').sum()}")
    print(f"[DELIVERY] Filtered out (< {minimum_average:.1f}%): {(audit['DeliveryStatus'] == 'FILTERED_OUT_LT_60_PERCENT').sum()}")
    print(f"[DELIVERY] Audit saved: {audit_path}")

    # Restore original candidate columns plus audit metrics.
    metric_cols = [c for c in audit.columns if c not in candidates.columns]
    qualified_symbols = qualified[[symbol_col] + metric_cols].copy()
    output = candidates.merge(qualified_symbols, on=symbol_col, how="inner")
    return output, audit
