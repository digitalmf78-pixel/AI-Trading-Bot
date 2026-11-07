"""NSE EOD five-session delivery filter and category audit.

Category A passes when the five-session average Delivery % is >= 60.00%.
The downstream gate passes only when each of those five sessions is >= 60.00%.
The average-based category remains available for comparison and collection reports.
Use the latest five distinct valid reports dated on or before the EOD as-of date.
If the current day's report has not been published, skip that unavailable date,
log it, and use prior valid reports; never relabel old data as current-day data.
Fewer than five valid distinct reports means WAIT_FOR_DATA.
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
MINIMUM_DAILY_DELIVERY = 60.0
MAX_REPORT_AGE_DAYS = 7
# Compatibility alias for existing callers; this threshold is applied to EACH day.
MINIMUM_AVERAGE = MINIMUM_DAILY_DELIVERY
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


def get_delivery_sessions(asof_date, required_sessions: int = 5, max_calendar_days: int = 30,
                          session: requests.Session | None = None,
                          collect_all: bool = False) -> list[tuple[date, pd.DataFrame]]:
    """Return distinct valid NSE delivery reports within the calendar lookback.

    collect_all=True scans the complete lookback window and returns every
    valid report. This lets 30D A/B classification and 5D/10D/20D analysis
    share one download/cache pass. Legacy early-stop remains the default.
    """
    asof = _parse_date(asof_date)
    http = session or requests.Session()
    http.headers.update(HEADERS)
    found: list[tuple[date, pd.DataFrame]] = []
    seen: set[date] = set()
    for offset in range(max_calendar_days + 1):
        day = asof - timedelta(days=offset)
        if day.weekday() >= 5:
            continue
        frame = _read_cached_or_download(http, day)
        if frame is None:
            if offset == 0:
                print(
                    f"[DELIVERY] As-of report {asof.isoformat()} is not available yet; "
                    f"searching backward across {max_calendar_days} calendar days."
                )
            continue
        if day in seen:
            continue
        frame = frame.copy()
        frame["REPORT_DATE"] = day.isoformat()
        found.append((day, frame))
        seen.add(day)
        print(f"[DELIVERY] Accepted report {day}: {len(frame)} rows ({len(found)} valid sessions)")
        if not collect_all and len(found) >= required_sessions:
            break
    if len(found) < required_sessions:
        raise RuntimeError(
            f"WAIT_FOR_DATA: only {len(found)}/{required_sessions} distinct delivery reports "
            f"found by {asof.isoformat()} within {max_calendar_days} calendar days"
        )
    found.sort(key=lambda item: item[0])
    print(
        f"[DELIVERY CACHE] Window={max_calendar_days} calendar days; "
        f"valid reports={len(found)}; mode={'complete-window' if collect_all else 'early-stop'}."
    )
    return found
def apply_delivery_filter(candidates: pd.DataFrame, asof_date, symbol_col: str = "TckrSymb",
                          series_col: str = "SctySrs", minimum_average: float = MINIMUM_AVERAGE,
                          sessions: list[tuple[date, pd.DataFrame]] | None = None,
                          http_session: requests.Session | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Classify Category A/B over all valid reports in the 30-calendar-day window.

    Category A: average Delivery % across each candidate's valid reports >=60%.
    Category B: every one of that candidate's valid reports is >=60%.
    Each candidate needs at least five valid distinct report dates; otherwise
    both categories remain WAIT_FOR_DATA. Exactly 60.00% passes.
    """
    if candidates.empty:
        return candidates.copy(), pd.DataFrame()
    if symbol_col not in candidates.columns:
        raise ValueError(f"Candidate symbol column missing: {symbol_col}")

    threshold = float(minimum_average)
    asof = _parse_date(asof_date)
    try:
        reports = sessions if sessions is not None else get_delivery_sessions(
            asof, required_sessions=5, max_calendar_days=30,
            session=http_session, collect_all=True,
        )
        reports = sorted(
            {day: frame for day, frame in reports if day <= asof}.items(),
            key=lambda item: item[0],
        )
        if len(reports) < 5:
            raise RuntimeError(
                f"WAIT_FOR_DATA: only {len(reports)}/5 distinct valid delivery sessions in 30 days"
            )
    except RuntimeError as exc:
        if "WAIT_FOR_DATA" not in str(exc):
            raise
        print(f"[DELIVERY] {exc}")
        audit = candidates.copy()
        audit["DeliverySessions"] = 0
        audit["DeliveryDailyPassCount"] = 0
        audit["DeliveryMin30D"] = float("nan")
        audit["AvgDelivery30D"] = float("nan")
        audit["DeliveryMin5D"] = float("nan")
        audit["AvgDelivery5D"] = float("nan")
        audit["LatestDeliveryPct"] = float("nan")
        audit["DeliveryCategoryAStatus"] = "WAIT_FOR_DATA"
        audit["DeliveryCategoryBStatus"] = "WAIT_FOR_DATA"
        audit["DeliveryStatus"] = "WAIT_FOR_DATA"
        audit["DeliveryFilterStatus"] = "WAIT_FOR_DATA"
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        audit.to_csv(AUDIT_DIR / f"delivery_dual_category_audit_{asof.strftime('%Y%m%d')}.csv", index=False)
        audit.to_csv(AUDIT_DIR / f"delivery_first_audit_{asof.strftime('%Y%m%d')}.csv", index=False)
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
        duplicate_keys = frame.duplicated(["SYMBOL", "SERIES"], keep=False)
        if duplicate_keys.any():
            frame = frame.loc[~duplicate_keys].copy()
        pieces.append(frame)

    all_delivery = pd.concat(
        pieces, ignore_index=True
    ) if pieces else pd.DataFrame(columns=["SYMBOL", "SERIES", "DELIV_PER", "REPORT_DATE"])
    candidate = candidates.copy()
    candidate["_SYMBOL_KEY"] = candidate[symbol_col].astype(str).str.strip().str.upper()
    candidate["_SERIES_KEY"] = (
        candidate[series_col].astype(str).str.strip().str.upper()
        if series_col in candidate.columns else "EQ"
    )
    report_dates = [day.isoformat() for day, _ in reports]
    latest_valid_report_date = reports[-1][0].isoformat()
    asof_report_available = asof.isoformat() in report_dates
    report_age_days = (asof - reports[-1][0]).days
    window_stale = report_age_days > MAX_REPORT_AGE_DAYS
    audits = []
    for _, row in candidate.iterrows():
        sym, ser = row["_SYMBOL_KEY"], row["_SERIES_KEY"]
        matches = all_delivery[
            (all_delivery["SYMBOL"] == sym) & (all_delivery["SERIES"] == ser)
        ]
        by_date = {str(r["REPORT_DATE"]): float(r["DELIV_PER"]) for _, r in matches.iterrows()}
        values = [by_date[day] for day in report_dates if day in by_date]
        count = len(values)
        avg = float(sum(values) / count) if count >= 5 else float("nan")
        daily_pass_count = sum(v >= threshold for v in values)
        daily_min = min(values) if count >= 5 else float("nan")
        if count < 5:
            category_a = category_b = overall = "WAIT_FOR_DATA"
        else:
            category_a = (
                "PASS_AVG_GE_60_PERCENT" if avg >= threshold
                else "FILTERED_OUT_AVG_LT_60_PERCENT"
            )
            category_b = (
                "PASS_EACH_DAY_GE_60_PERCENT" if all(v >= threshold for v in values)
                else "FILTERED_OUT_AT_LEAST_ONE_DAY_LT_60_PERCENT"
            )
            overall = (
                "PASS_A_OR_B" if category_a == "PASS_AVG_GE_60_PERCENT"
                or category_b == "PASS_EACH_DAY_GE_60_PERCENT"
                else "FILTERED_OUT_LT_60_PERCENT"
            )
        if window_stale:
            category_a = category_b = overall = "WAIT_FOR_DATA_STALE_REPORT"

        record = row.drop(labels=["_SYMBOL_KEY", "_SERIES_KEY"]).to_dict()
        record.update({
            "DeliverySessions": count,
            "DeliveryDailyPassCount": daily_pass_count,
            "DeliveryMin30D": daily_min,
            "AvgDelivery30D": avg,
            # Compatibility aliases now describe the complete 30-calendar-day window.
            "DeliveryMin5D": daily_min,
            "AvgDelivery5D": avg,
            "LatestDeliveryPct": by_date.get(latest_valid_report_date, float("nan")),
            "DeliveryAsOfDate": asof.isoformat(),
            "DeliveryAsOfReportAvailable": asof_report_available,
            "DeliveryReportAgeDays": report_age_days,
            "DeliveryWindowStale": window_stale,
            "DeliveryWindowStartDate": report_dates[0],
            "DeliveryWindowEndDate": report_dates[-1],
            "DeliveryCategoryAStatus": category_a,
            "DeliveryCategoryBStatus": category_b,
            "DeliveryStatus": overall,
            "DeliveryFilterStatus": overall,
        })
        for report_date in report_dates:
            record[f"Delivery_{report_date}"] = by_date.get(report_date, float("nan"))
        audits.append(record)

    audit = pd.DataFrame(audits)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    audit_path = AUDIT_DIR / f"delivery_dual_category_audit_{asof.strftime('%Y%m%d')}.csv"
    audit.to_csv(audit_path, index=False)
    category_a = audit[audit["DeliveryCategoryAStatus"] == "PASS_AVG_GE_60_PERCENT"].copy()
    category_b = audit[audit["DeliveryCategoryBStatus"] == "PASS_EACH_DAY_GE_60_PERCENT"].copy()
    category_a.to_csv(AUDIT_DIR / "v8_delivery_category_a_avg60.csv", index=False)
    category_b.to_csv(AUDIT_DIR / "v8_delivery_category_b_each_day60.csv", index=False)
    audit.to_csv(AUDIT_DIR / f"delivery_first_audit_{asof.strftime('%Y%m%d')}.csv", index=False)
    print(f"[DELIVERY] 30D Category A average >= {threshold:.2f}%: {len(category_a)}")
    print(f"[DELIVERY] 30D Category B every valid session >= {threshold:.2f}%: {len(category_b)}")
    print(f"[DELIVERY] WAIT_FOR_DATA (<5 candidate sessions): {(audit['DeliveryStatus'].astype(str).str.startswith('WAIT_FOR_DATA')).sum()}")
    print(f"[DELIVERY] 30D dual-category audit saved: {audit_path}")

    metric_cols = [col for col in audit.columns if col not in candidates.columns]
    qualified_symbols = audit.loc[
        audit["DeliveryFilterStatus"].isin(["PASS_A_OR_B", "PASS_GE_60_PERCENT"]),
        [symbol_col] + metric_cols,
    ].copy()
    output = candidates.merge(qualified_symbols, on=symbol_col, how="inner")
    return output, audit

