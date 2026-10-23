"""Point-in-time verification of NSE financial-results publication dates.

A record is VERIFIED only when an official NSE filing matches the exact symbol
and reported period end, and the broadcast/publication date is no later than the
requested EOD cutoff. Fetch failures never remove candidates or invent dates.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
from typing import Callable

import pandas as pd

OUTPUT_DIR = Path("outputs")
FILINGS_CACHE = OUTPUT_DIR / "v8_official_financial_results_filings.csv"
VERIFY_DIAGNOSTICS = OUTPUT_DIR / "v8_official_publication_date_verification.csv"
NSE_HOME = "https://www.nseindia.com/"
NSE_API = "https://www.nseindia.com/api/corporate-announcements"
NSE_FILINGS_PAGE = "https://www.nseindia.com/companies-listing/corporate-filings-announcements"


def _date(value):
    """Parse common NSE date strings without guessing ambiguous numeric dates.

    Supports ISO dates, NSE day-first strings, month-first announcement strings,
    timestamps, and Unix epoch seconds/milliseconds. Ambiguous slash dates are
    interpreted day-first first because NSE announcement dates are day-first.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            number = float(value)
            if number > 10**12:
                parsed = pd.to_datetime(number, unit="ms", utc=True, errors="coerce")
            elif number > 10**9:
                parsed = pd.to_datetime(number, unit="s", utc=True, errors="coerce")
            else:
                return None
            return None if pd.isna(parsed) else parsed.date()
        except (ValueError, TypeError, OverflowError):
            return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "nat", "<na>"}:
        return None
    # Normalize ordinal suffixes, e.g. 30th June 2026.
    text = re.sub(r"(?i)\b(\d{1,2})(st|nd|rd|th)\b", r"\1", text)
    # ISO is unambiguous. Slash-separated NSE dates are day-first when valid;
    # if that interpretation is impossible (e.g. 06/30/2026), fall back to
    # month-first. Named-month strings are parsed after these explicit cases.
    parsed = pd.to_datetime(text, format="%Y-%m-%d", errors="coerce")
    if not pd.isna(parsed):
        return parsed.date()
    if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", text):
        first, second, _year = (int(part) for part in text.split("/"))
        # If only one interpretation is valid, choose it. For truly ambiguous
        # dates (both values <= 12), follow NSE's day-first convention.
        dayfirst = not (second > 12 and first <= 12)
        parsed = pd.to_datetime(text, dayfirst=dayfirst, errors="coerce")
        if not pd.isna(parsed):
            return parsed.date()
    for dayfirst in (True, False):
        parsed = pd.to_datetime(text, errors="coerce", dayfirst=dayfirst)
        if not pd.isna(parsed):
            return parsed.date()
    return None


def _period_end_from_description(description: str):
    """Extract a date only when it is explicitly tied to a financial period end.

    Handles common NSE wording including ordinal dates and combined quarter/year
    periods. It deliberately refuses a meeting date or an arbitrary date.
    """
    text = str(description or "")
    normalized = re.sub(r"(?i)\b(\d{1,2})(st|nd|rd|th)\b", r"\1", text)
    # Dates in the three common formats seen in corporate-announcement subjects.
    date_pattern = (
        r"(\d{1,2}[-/]\d{1,2}[-/]\d{4})"
        r"|((?:\d{1,2})[- ]+[A-Za-z]{3,9}[- ,]+\d{4})"
        r"|([A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})"
    )
    # The period words may be combined ("quarter and year", "quarter and
    # nine months"). The date must immediately follow an explicit 'ended'.
    pattern = re.compile(
        r"(?:period|quarter|year|nine\s+months|half\s+year|three\s+months)"
        r"(?:\s+(?:and|/|&)?\s*(?:period|quarter|year|nine\s+months|half\s+year|three\s+months))*"
        r"\s+ended\s+(?:on\s+)?(?:" + date_pattern + r")",
        flags=re.IGNORECASE,
    )
    match = pattern.search(normalized)
    if not match:
        return None
    date_text = next((group for group in match.groups() if group), "")
    return _date(date_text)


def _announcement_date(item: dict):
    for key in ("an_dt", "announcementDate", "date", "sort_date", "timestamp", "broadcastDate", "broadcast_date"):
        if item.get(key):
            d = _date(item[key])
            if d:
                return d
    return None


def _announcement_symbol(item: dict):
    for key in ("symbol", "sm_symbol", "ticker", "TckrSymb"):
        value = str(item.get(key, "")).strip().upper()
        if value and value not in {"NAN", "NONE"}:
            return value
    return ""


def _announcement_description(item: dict):
    return " ".join(str(item.get(k, "") or "") for k in ("desc", "subject", "sm_name", "details", "description")).strip()


def _announcement_period_end(item: dict, description: str):
    # Prefer explicit period-end fields from the structured response.
    for key in ("period", "periodEnd", "period_end", "periodEnded", "period_ended", "financialPeriodEnd", "financial_period_end"):
        if item.get(key):
            d = _date(item[key])
            if d:
                return d
    return _period_end_from_description(description)


def _unwrap_nse_payload(payload):
    """Normalize the common NSE response wrappers into a list of announcement dicts."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "rows", "announcements", "records"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    raise ValueError("Unexpected NSE corporate-announcements response schema")


def fetch_nse_financial_results(
    asof_date,
    lookback_days: int = 450,
    session_factory=None,
    window_days: int = 30,
):
    """Fetch NSE corporate announcements in small date windows through EOD.

    NSE's announcements endpoint can return incomplete/large responses for a
    long single request. Fetch bounded windows, keep partial successes, and
    expose request/parser counts in DataFrame.attrs for the audit report.
    A filing is returned only when its own announcement explicitly identifies
    a financial period end; publication date is never substituted for period.
    """
    import requests

    cutoff = pd.to_datetime(asof_date, errors="coerce")
    if pd.isna(cutoff):
        raise ValueError(f"Invalid asof_date: {asof_date}")
    end_date = cutoff.date()
    start_date = end_date - timedelta(days=max(1, int(lookback_days)))
    window_days = max(7, int(window_days))
    session = session_factory() if session_factory else requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": NSE_FILINGS_PAGE,
    })
    home = session.get(NSE_HOME, timeout=20)
    home.raise_for_status()

    rows = []
    failed_windows = []
    total_announcement_rows = 0
    financial_subject_rows = 0
    dated_financial_rows = 0
    period_parsed_rows = 0
    window_count = 0
    window_start = start_date
    while window_start <= end_date:
        window_end = min(end_date, window_start + timedelta(days=window_days - 1))
        params = {
            "index": "equities",
            "from_date": window_start.strftime("%d-%m-%Y"),
            "to_date": window_end.strftime("%d-%m-%Y"),
        }
        window_count += 1
        try:
            response = session.get(NSE_API, params=params, timeout=30)
            response.raise_for_status()
            payload = _unwrap_nse_payload(response.json())
            total_announcement_rows += len(payload)
        except Exception as exc:
            failed_windows.append({
                "from_date": params["from_date"],
                "to_date": params["to_date"],
                "error": f"{type(exc).__name__}: {exc}"[:250],
            })
            window_start = window_end + timedelta(days=1)
            continue

        for item in payload:
            if not isinstance(item, dict):
                continue
            desc = _announcement_description(item)
            lower = desc.lower()
            if not any(term in lower for term in (
                "financial results", "financial result", "unaudited results",
                "audited results", "integrated filing - financial",
                "financial results for",
            )):
                continue
            financial_subject_rows += 1
            pub_date = _announcement_date(item)
            if not pub_date or pub_date > end_date or pub_date < window_start or pub_date > window_end:
                continue
            dated_financial_rows += 1
            symbol = _announcement_symbol(item)
            period_end = _announcement_period_end(item, desc)
            if not symbol or not period_end:
                continue
            period_parsed_rows += 1
            attachment = str(
                item.get("attchmntFile")
                or item.get("attachment")
                or item.get("attachmentFile")
                or item.get("url")
                or ""
            ).strip()
            if attachment.startswith("/"):
                attachment = "https://www.nseindia.com" + attachment
            if not attachment.startswith(("https://", "http://")):
                attachment = NSE_FILINGS_PAGE
            rows.append({
                "TckrSymb": symbol,
                "FinancialPeriodEnd": period_end.isoformat(),
                "PublicationDate": pub_date.isoformat(),
                "PublicationDateStatus": "VERIFIED",
                "FilingDescription": desc,
                "OfficialFilingURL": attachment,
                "OfficialSource": "NSE corporate announcements",
                "RetrievedAtUTC": datetime.now(timezone.utc).isoformat(),
                "FetchWindowStart": window_start.isoformat(),
                "FetchWindowEnd": window_end.isoformat(),
            })
        window_start = window_end + timedelta(days=1)

    columns = [
        "TckrSymb", "FinancialPeriodEnd", "PublicationDate",
        "PublicationDateStatus", "FilingDescription", "OfficialFilingURL",
        "OfficialSource", "RetrievedAtUTC", "FetchWindowStart", "FetchWindowEnd",
    ]
    result = pd.DataFrame(rows, columns=columns)
    if not result.empty:
        result = result.drop_duplicates(
            subset=["TckrSymb", "FinancialPeriodEnd", "PublicationDate", "OfficialFilingURL"],
            keep="last",
        ).reset_index(drop=True)
    result.attrs["fetch_summary"] = {
        "RequestedStartDate": start_date.isoformat(),
        "RequestedEndDate": end_date.isoformat(),
        "WindowDays": window_days,
        "WindowsAttempted": window_count,
        "WindowsFailed": len(failed_windows),
        "AnnouncementRows": total_announcement_rows,
        "FinancialSubjectRows": financial_subject_rows,
        "FinancialRowsWithDate": dated_financial_rows,
        "RowsWithParsedPeriodEnd": period_parsed_rows,
        "MatchedFilingRows": len(result),
        "FailedWindows": failed_windows[:20],
    }
    if failed_windows and not rows:
        raise RuntimeError(
            f"All/remaining NSE announcement windows failed; "
            f"windows_failed={len(failed_windows)}/{window_count}; "
            f"first_error={failed_windows[0]['error']}"
        )
    return result


def apply_official_publication_dates(records: pd.DataFrame, asof_date, filings: pd.DataFrame | None = None,
                                    fetcher: Callable | None = None, cache_path=FILINGS_CACHE,
                                    diagnostics_path=VERIFY_DIAGNOSTICS):
    """Annotate publication dates; preserve every input row and every metric."""
    output = records.copy()
    if "TckrSymb" not in output:
        output["TckrSymb"] = ""
    defaults = {
        "FinancialPeriodEnd": pd.NA, "PublicationDate": pd.NA,
        "PublicationDateStatus": "UNVERIFIED", "OfficialFilingURL": pd.NA,
        "OfficialFilingSource": pd.NA,
    }
    for col, default in defaults.items():
        if col not in output:
            output[col] = default
    cutoff = pd.to_datetime(asof_date, errors="coerce")
    if pd.isna(cutoff):
        raise ValueError(f"Invalid asof_date: {asof_date}")
    cutoff = cutoff.normalize()
    output["TckrSymb"] = output["TckrSymb"].astype(str).str.strip().str.upper()
    output["FinancialPeriodEndParsed"] = pd.to_datetime(output["FinancialPeriodEnd"], errors="coerce").dt.normalize()
    output["PublicationDateParsed"] = pd.to_datetime(output["PublicationDate"], errors="coerce").dt.normalize()
    existing_verified = output["PublicationDateStatus"].astype(str).str.upper().eq("VERIFIED")
    stale = existing_verified & (
        output["FinancialPeriodEndParsed"].isna() | output["FinancialPeriodEndParsed"].gt(cutoff) |
        output["PublicationDateParsed"].isna() | output["PublicationDateParsed"].gt(cutoff)
    )
    output.loc[stale, "PublicationDateStatus"] = "UNVERIFIED"
    output.loc[stale, "PublicationDate"] = pd.NA
    diagnostics = []
    cache_file = Path(cache_path)
    fetch_error = None
    if filings is None:
        try:
            fetched = (fetcher or fetch_nse_financial_results)(cutoff.date().isoformat())
            if fetched is None:
                fetched = pd.DataFrame()
            fetch_summary = getattr(fetched, "attrs", {}).get("fetch_summary", {})
            if fetch_summary:
                diagnostics.append({"Status": "LIVE_FETCH_SUMMARY", **fetch_summary})
                if int(fetch_summary.get("WindowsFailed", 0) or 0):
                    diagnostics.append({
                        "Status": "LIVE_FETCH_PARTIAL",
                        "Reason": "Some NSE announcement windows failed; successful windows were retained",
                        "WindowsFailed": fetch_summary.get("WindowsFailed"),
                        "WindowsAttempted": fetch_summary.get("WindowsAttempted"),
                    })
            if not fetched.empty:
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                fetched.to_csv(cache_file, index=False)
                filings = fetched
            else:
                # Keep the counters: an empty parsed result can mean no financial
                # announcements, a changed NSE schema, or descriptions without
                # parseable period-end dates. Do not erase a useful prior cache.
                filings = pd.DataFrame()
                diagnostics.append({
                    "Status": "LIVE_FETCH_EMPTY",
                    "Reason": "No filing rows with an explicit financial period end were parsed",
                    "AnnouncementRows": fetch_summary.get("AnnouncementRows", pd.NA),
                    "FinancialSubjectRows": fetch_summary.get("FinancialSubjectRows", pd.NA),
                    "FinancialRowsWithDate": fetch_summary.get("FinancialRowsWithDate", pd.NA),
                    "RowsWithParsedPeriodEnd": fetch_summary.get("RowsWithParsedPeriodEnd", pd.NA),
                })
        except Exception as exc:
            fetch_error = f"{type(exc).__name__}: {exc}"[:500]
            diagnostics.append({"Status": "FETCH_FAILED", "Reason": fetch_error})
            filings = pd.DataFrame()

        if (filings is None or filings.empty) and cache_file.exists() and cache_file.stat().st_size:
            try:
                cached = pd.read_csv(cache_file)
                if not cached.empty:
                    filings = cached
                    diagnostics.append({
                        "Status": "CUTOFF_SAFE_CACHE_FALLBACK",
                        "Reason": "Using cached official filing records; publication/period dates are filtered against the requested EOD cutoff",
                        "CachePath": str(cache_file),
                        "CachedRows": len(cached),
                    })
            except Exception as cache_exc:
                diagnostics.append({"Status": "CACHE_READ_FAILED", "Reason": f"{type(cache_exc).__name__}: {cache_exc}"[:300]})

    if filings is None or filings.empty:
        for _, row in output.iterrows():
            diagnostics.append({"TckrSymb": row.get("TckrSymb", ""), "Status": "UNVERIFIED", "Reason": "No official filing data available; publication date not inferred"})
        Path(diagnostics_path).parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(diagnostics).to_csv(diagnostics_path, index=False)
        return output.drop(columns=["FinancialPeriodEndParsed", "PublicationDateParsed"], errors="ignore")

    filings = filings.copy()
    for col in ("TckrSymb", "FinancialPeriodEnd", "PublicationDate", "PublicationDateStatus", "OfficialFilingURL", "OfficialSource"):
        if col not in filings:
            filings[col] = pd.NA
    filings["TckrSymb"] = filings["TckrSymb"].astype(str).str.strip().str.upper()
    filings["FinancialPeriodEndParsed"] = pd.to_datetime(filings["FinancialPeriodEnd"], errors="coerce").dt.normalize()
    filings["PublicationDateParsed"] = pd.to_datetime(filings["PublicationDate"].map(_date), errors="coerce").dt.normalize()
    verified = filings[filings["PublicationDateStatus"].astype(str).str.upper().eq("VERIFIED")].copy()
    verified = verified.dropna(subset=["FinancialPeriodEndParsed", "PublicationDateParsed"])
    verified = verified[(verified["FinancialPeriodEndParsed"] <= cutoff) & (verified["PublicationDateParsed"] <= cutoff)]
    verified = verified.sort_values("PublicationDateParsed").drop_duplicates(["TckrSymb", "FinancialPeriodEndParsed"], keep="last")
    index = {(r["TckrSymb"], r["FinancialPeriodEndParsed"]): r for _, r in verified.iterrows()}

    for idx, row in output.iterrows():
        symbol = str(row.get("TckrSymb", "")).strip().upper()
        period = pd.to_datetime(row.get("FinancialPeriodEnd", pd.NA), errors="coerce")
        if not symbol or pd.isna(period):
            diagnostics.append({"TckrSymb": symbol, "Status": "UNVERIFIED", "Reason": "Missing reported FinancialPeriodEnd; AsOfDate is not a substitute"})
            output.at[idx, "PublicationDateStatus"] = "UNVERIFIED"
            continue
        period = period.normalize()
        if period > cutoff:
            diagnostics.append({"TckrSymb": symbol, "FinancialPeriodEnd": period.date().isoformat(), "Status": "UNVERIFIED", "Reason": "Financial period ends after EOD cutoff"})
            output.at[idx, "PublicationDateStatus"] = "UNVERIFIED"
            continue
        filing = index.get((symbol, period))
        if filing is None:
            diagnostics.append({"TckrSymb": symbol, "FinancialPeriodEnd": period.date().isoformat(), "Status": "UNVERIFIED", "Reason": "No exact official symbol + period-end match"})
            # Preserve a previously verified and point-in-time-valid date only if it remains valid.
            continue
        pub = filing["PublicationDateParsed"]
        output.at[idx, "PublicationDate"] = pub.date().isoformat()
        output.at[idx, "PublicationDateStatus"] = "VERIFIED"
        output.at[idx, "OfficialFilingURL"] = filing.get("OfficialFilingURL", NSE_FILINGS_PAGE)
        output.at[idx, "OfficialFilingSource"] = filing.get("OfficialSource", "NSE corporate announcements")
        diagnostics.append({"TckrSymb": symbol, "FinancialPeriodEnd": period.date().isoformat(), "PublicationDate": pub.date().isoformat(), "Status": "VERIFIED", "OfficialFilingURL": output.at[idx, "OfficialFilingURL"]})
    Path(diagnostics_path).parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(diagnostics).to_csv(diagnostics_path, index=False)
    print(f"[FUNDAMENTAL OFFICIAL DATE] verified={int(output['PublicationDateStatus'].astype(str).str.upper().eq('VERIFIED').sum())}; candidates={len(output)}; unmatched remain UNVERIFIED")
    return output.drop(columns=["FinancialPeriodEndParsed", "PublicationDateParsed"], errors="ignore")
