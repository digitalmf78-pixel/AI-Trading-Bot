"""NSE EOD five-session delivery-first shortlist filter.

Rule: each of the latest five distinct valid NSE trading sessions must have
Delivery % >= 60.00%. Average delivery is retained for reporting only and never
determines eligibility. Missing/invalid session data never PASS.
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
    """Annotate two independent Delivery categories and return Category-A pass rows.

    Category A: average DELIV_PER across the latest five distinct valid sessions >= 60%.
    Category B: each of those five sessions individually >= 60%.
    Both require five valid session records. Missing data is WAIT_FOR_DATA.
    Category B is reported separately; it is naturally a subset of Category A.
    """
    if candidates.empty:
        return candidates.copy(), pd.DataFrame()
    if symbol_col not in candidates.columns:
        raise ValueError(f"Candidate symbol column missing: {symbol_col}")

    threshold = float(minimum_average)
    try:
        reports = sessions if sessions is not None else get_delivery_sessions(asof_date, 5, session=http_session)
        if len({day for day, _ in reports}) < 5:
            raise RuntimeError("WAIT_FOR_DATA: fewer than five distinct delivery sessions")
        reports = sorted(reports, key=lambda item: item[0])[-5:]
        if len({day for day, _ in reports}) != 5:
            raise RuntimeError("WAIT_FOR_DATA: exactly five distinct delivery sessions required")
    except RuntimeError as exc:
        if "WAIT_FOR_DATA" not in str(exc):
            raise
        print(f"[DELIVERY] {exc}")
        audit = candidates.copy()
        audit["DeliverySessions"] = 0
        audit["DeliveryDailyPassCount"] = 0
        audit["DeliveryMin5D"] = float("nan")
        audit["AvgDelivery5D"] = float("nan")
        audit["LatestDeliveryPct"] = float("nan")
        audit["DeliveryCategoryAStatus"] = "WAIT_FOR_DATA"
        audit["DeliveryCategoryBStatus"] = "WAIT_FOR_DATA"
        audit["DeliveryStatus"] = "WAIT_FOR_DATA"
        audit["DeliveryFilterStatus"] = "WAIT_FOR_DATA"
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        audit.to_csv(AUDIT_DIR / f"delivery_dual_category_audit_{_parse_date(asof_date).strftime('%Y%m%d')}.csv", index=False)
        audit.to_csv(AUDIT_DIR / f"delivery_first_audit_{_parse_date(asof_date).strftime('%Y%m%d')}.csv", index=False)
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
        # Duplicates for a symbol/series/day are ambiguous and cannot qualify.
        duplicate_keys = frame.duplicated(["SYMBOL", "SERIES"], keep=False)
        if duplicate_keys.any():
            frame = frame.loc[~duplicate_keys].copy()
        pieces.append(frame)

    all_delivery = pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame(columns=["SYMBOL", "SERIES", "DELIV_PER", "REPORT_DATE"])
    candidate = candidates.copy()
    candidate["_SYMBOL_KEY"] = candidate[symbol_col].astype(str).str.strip().str.upper()
    candidate["_SERIES_KEY"] = candidate[series_col].astype(str).str.strip().str.upper() if series_col in candidate.columns else "EQ"
    report_dates = [day.isoformat() for day, _ in reports]
    audits = []
    for _, row in candidate.iterrows():
        sym, ser = row["_SYMBOL_KEY"], row["_SERIES_KEY"]
        matches = all_delivery[(all_delivery["SYMBOL"] == sym) & (all_delivery["SERIES"] == ser)]
        by_date = {str(r["REPORT_DATE"]): float(r["DELIV_PER"]) for _, r in matches.iterrows()}
        values = [by_date[d] for d in report_dates if d in by_date]
        count = len(values)
        avg = float(sum(values) / 5) if count == 5 else float("nan")
        daily_pass_count = sum(v >= threshold for v in values)
        daily_min = min(values) if count == 5 else float("nan")
        if count != 5:
            category_a = category_b = "WAIT_FOR_DATA"
            overall = "WAIT_FOR_DATA"
        else:
            category_a = "PASS_AVG_GE_60_PERCENT" if avg >= threshold else "FILTERED_OUT_AVG_LT_60_PERCENT"
            category_b = "PASS_EACH_DAY_GE_60_PERCENT" if all(v >= threshold for v in values) else "FILTERED_OUT_AT_LEAST_ONE_DAY_LT_60_PERCENT"
            # Main pipeline continues on Category A; Category B remains an independent report.
            overall = "PASS_GE_60_PERCENT" if category_a == "PASS_AVG_GE_60_PERCENT" else "FILTERED_OUT_LT_60_PERCENT"
        record = row.drop(labels=["_SYMBOL_KEY", "_SERIES_KEY"]).to_dict()
        record.update({
            "DeliverySessions": count,
            "DeliveryDailyPassCount": daily_pass_count,
            "DeliveryMin5D": daily_min,
            "AvgDelivery5D": avg,
            "LatestDeliveryPct": by_date.get(_parse_date(asof_date).isoformat(), float("nan")),
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
    audit_path = AUDIT_DIR / f"delivery_dual_category_audit_{_parse_date(asof_date).strftime('%Y%m%d')}.csv"
    audit.to_csv(audit_path, index=False)
    # Category-specific standalone outputs make the two conditions easy to compare.
    category_a = audit[audit["DeliveryCategoryAStatus"] == "PASS_AVG_GE_60_PERCENT"].copy()
    category_b = audit[audit["DeliveryCategoryBStatus"] == "PASS_EACH_DAY_GE_60_PERCENT"].copy()
    category_a.to_csv(AUDIT_DIR / "v8_delivery_category_a_avg60.csv", index=False)
    category_b.to_csv(AUDIT_DIR / "v8_delivery_category_b_each_day60.csv", index=False)
    # Compatibility report path used by earlier project dashboards.
    audit.to_csv(AUDIT_DIR / f"delivery_first_audit_{_parse_date(asof_date).strftime('%Y%m%d')}.csv", index=False)
    print(f"[DELIVERY] Category A average >= {threshold:.2f}%: {len(category_a)}")
    print(f"[DELIVERY] Category B every day >= {threshold:.2f}%: {len(category_b)}")
    print(f"[DELIVERY] WAIT_FOR_DATA: {(audit['DeliveryStatus'] == 'WAIT_FOR_DATA').sum()}")
    print(f"[DELIVERY] Dual-category audit saved: {audit_path}")

    metric_cols = [col for col in audit.columns if col not in candidates.columns]
    qualified_symbols = category_a[[symbol_col] + metric_cols].copy()
    output = candidates.merge(qualified_symbols, on=symbol_col, how="inner")
    return output, audit
