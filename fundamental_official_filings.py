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
FETCH_DIAGNOSTICS = OUTPUT_DIR / "v8_official_fetch_diagnostics.csv"
NSE_HOME = "https://www.nseindia.com/"
NSE_API = "https://www.nseindia.com/api/corporate-announcements"  # legacy fallback only
NSE_RESULTS_API = "https://www.nseindia.com/api/integrated-filing-results"
NSE_FILINGS_PAGE = "https://www.nseindia.com/companies-listing/corporate-integrated-filing"


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
        r"\s+ended\s+(?:" + date_pattern + r")",
        flags=re.IGNORECASE,
    )
    match = pattern.search(normalized)
    if not match:
        return None
    date_text = next((group for group in match.groups() if group), "")
    return _date(date_text)


def _announcement_date(item: dict):
    for key in ("creation_Date", "creationDate", "broadCastDate", "broadcastDate", "broadcast_date", "filingDate", "filing_date", "an_dt", "announcementDate", "date", "sort_date", "timestamp"):
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
    return " ".join(str(item.get(k, "") or "") for k in ("subject", "relatingTo", "desc", "sm_name", "companyName", "cmName", "company_name", "details", "description", "financialYear", "type_Sub", "typeSub", "filing_type", "consolidated", "audited")).strip()


def _announcement_period_end(item: dict, description: str):
    # Prefer explicit period-end fields from the structured response.
    for key in ("qe_Date", "qeDate", "quarter_ended", "quarterEnded", "period_ended", "periodEnded", "periodEnd", "period_end", "period_end_date", "financialPeriodEnd", "financial_period_end", "FinancialPeriodEnd", "toDate", "to_date", "re_to_dt"):
        if item.get(key):
            d = _date(item[key])
            if d:
                return d
    return _period_end_from_description(description)


def _extract_result_items(payload):
    """Return filing rows plus wrapper metadata from common NSE JSON shapes."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)], {}, list(payload[0].keys()) if payload and isinstance(payload[0], dict) else []
    if not isinstance(payload, dict):
        return [], {}, []
    wrapper_keys = list(payload.keys())
    for key in ("data", "results", "records", "rows", "financialResults", "financial_results", "result"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)], payload, wrapper_keys
        if isinstance(value, dict):
            for nested_key in ("data", "results", "records", "rows"):
                nested = value.get(nested_key)
                if isinstance(nested, list):
                    return [item for item in nested if isinstance(item, dict)], payload, wrapper_keys
    return [], payload, wrapper_keys


def _first_value(item, keys):
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip() and str(value).strip().lower() not in {"none", "nan", "nat", "<na>"}:
            return value
    return None


def fetch_nse_financial_results(asof_date, lookback_days: int = 450, session_factory=None,
                                diagnostics_path=FETCH_DIAGNOSTICS):
    """Fetch NSE Integrated Filing-Financials using its observed JSON schema.

    The implementation follows the publicly documented working pattern used by
    the nse-market-scripts reference project: probe totalCount, query the
    Integrated Filing endpoint with period_ended=all, and read creation_Date,
    symbol and qe_Date.  It never invents missing dates.
    """
    import requests

    cutoff = pd.to_datetime(asof_date, errors="coerce")
    if pd.isna(cutoff):
        raise ValueError(f"Invalid asof_date: {asof_date}")
    end_date = cutoff.date()
    start_date = end_date - timedelta(days=max(1, int(lookback_days)))
    session = session_factory() if session_factory else requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": NSE_FILINGS_PAGE,
        "X-Requested-With": "XMLHttpRequest",
    })
    diagnostic = {
        "AsOfDate": end_date.isoformat(), "LookbackStart": start_date.isoformat(),
        "LookbackEnd": end_date.isoformat(), "Endpoint": NSE_RESULTS_API,
        "HomepageWarmupStatus": "NOT_ATTEMPTED", "APIStatusCode": pd.NA,
        "APIContentType": "", "PayloadType": "", "PayloadKeys": "",
        "PayloadItemCount": 0, "DictItems": 0, "DescriptionItems": 0,
        "FinancialTermMatches": 0, "PublicationDateParsed": 0, "WithinDateRange": 0,
        "SymbolParsed": 0, "PeriodEndParsed": 0, "AcceptedRows": 0,
        "RejectNoFinancialTerm": 0, "RejectDateMissingOrOutOfRange": 0,
        "RejectSymbolMissing": 0, "RejectPeriodMissing": 0,
        "SampleDescriptions": "", "SampleFinancialResultMatches": "",
        "SampleMatchedItemKeys": "", "SampleMatchedItemFields": "",
        "APIRequestParams": "", "PagesFetched": 0, "PaginationStopReason": "",
        "ReportedTotalCount": pd.NA, "Error": "",
    }

    def save_diagnostic():
        path = Path(diagnostics_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame([diagnostic]).to_csv(path, index=False)

    def base_params(page=0, size=1):
        # `period_ended=all` and zero-based page indexing are part of the
        # observed NSE endpoint contract; omitting them caused unrelated/empty
        # records in previous attempts.
        return {
            "index": "equities",
            "from_date": start_date.strftime("%d-%m-%Y"),
            "to_date": end_date.strftime("%d-%m-%Y"),
            "period_ended": "all",
            "type": "Integrated Filing- Financials",
            "page": page,
            "size": size,
        }

    try:
        # Warm-up is best effort; a homepage 403 is not itself a failed API call.
        try:
            home = session.get(NSE_HOME, timeout=20)
            diagnostic["HomepageWarmupStatus"] = f"HTTP_{getattr(home, 'status_code', 200)}"
        except Exception as exc:
            diagnostic["HomepageWarmupStatus"] = f"ERROR:{type(exc).__name__}"

        probe_params = base_params(page=0, size=1)
        diagnostic["APIRequestParams"] = str(probe_params)
        probe = session.get(NSE_RESULTS_API, params=probe_params, timeout=30)
        diagnostic["APIStatusCode"] = getattr(probe, "status_code", pd.NA)
        headers = getattr(probe, "headers", {}) or {}
        diagnostic["APIContentType"] = str(headers.get("Content-Type", headers.get("content-type", "")))[:150]
        probe.raise_for_status()
        probe_payload = probe.json()
        diagnostic["PayloadType"] = type(probe_payload).__name__
        probe_items, probe_meta, probe_keys = _extract_result_items(probe_payload)
        diagnostic["PayloadKeys"] = ";".join(map(str, probe_keys[:50]))
        total_value = _first_value(probe_meta, ("totalCount", "total_count", "totalRecords", "total_records", "total", "recordsFiltered", "totalCount"))
        try:
            total_count = int(total_value) if total_value is not None else None
        except (ValueError, TypeError):
            total_count = None
        diagnostic["ReportedTotalCount"] = total_count if total_count is not None else pd.NA

        if total_count == 0:
            diagnostic["PaginationStopReason"] = "TOTAL_COUNT_ZERO"
            diagnostic["Error"] = "NSE Integrated Filing API reported totalCount=0 for the requested date window"
            rows_payload = []
        elif total_count is not None:
            # Reference implementation uses totalCount+50 in one request to
            # avoid live-feed drift between page requests. If NSE caps size,
            # fall back to verified zero-based pages below.
            requested_size = min(max(total_count + 50, 1), 50000)
            fetch_params = base_params(page=0, size=requested_size)
            response = session.get(NSE_RESULTS_API, params=fetch_params, timeout=60)
            response.raise_for_status()
            payload = response.json()
            items, meta, top_keys = _extract_result_items(payload)
            diagnostic["PayloadKeys"] = ";".join(map(str, top_keys[:50])) or diagnostic["PayloadKeys"]
            diagnostic["PagesFetched"] = 1
            rows_payload = list(items)
            if len(rows_payload) >= total_count:
                diagnostic["PaginationStopReason"] = "PROBE_TOTALCOUNT_FETCHED"
            else:
                # Fallback if the server imposes a page-size cap. Page index is
                # zero-based. Deduplicate by NSE seq_Id where available.
                diagnostic["PaginationStopReason"] = "FALLBACK_PAGINATION_AFTER_SIZE_CAP"
                rows_payload = []
                seen = set()
                page_size = 1000
                max_pages = min((total_count // page_size) + 5, 200)
                for page in range(max_pages):
                    page_params = base_params(page=page, size=page_size)
                    page_response = session.get(NSE_RESULTS_API, params=page_params, timeout=60)
                    page_response.raise_for_status()
                    page_payload = page_response.json()
                    page_items, page_meta, page_keys = _extract_result_items(page_payload)
                    diagnostic["PagesFetched"] = page + 1
                    if not page_items:
                        diagnostic["PaginationStopReason"] = "EMPTY_PAGE_BEFORE_TOTALCOUNT"
                        break
                    added = 0
                    for item in page_items:
                        stable_id = _first_value(item, ("seq_Id", "seq_id", "seqId", "id"))
                        signature = str(stable_id) if stable_id is not None else "|".join(str(item.get(k, "")) for k in ("symbol", "creation_Date", "qe_Date", "type_Sub", "consolidated", "audited"))
                        if signature not in seen:
                            seen.add(signature)
                            rows_payload.append(item)
                            added += 1
                    if len(rows_payload) >= total_count:
                        diagnostic["PaginationStopReason"] = "TOTALCOUNT_REACHED"
                        break
                    if added == 0:
                        diagnostic["PaginationStopReason"] = "NO_NEW_RECORDS"
                        break
                else:
                    diagnostic["PaginationStopReason"] = "MAX_PAGE_LIMIT_REACHED"
                if len(rows_payload) < total_count:
                    diagnostic["Error"] = f"NSE reported {total_count} records but only {len(rows_payload)} unique records were fetched"
        else:
            # No totalCount in response: conservative page-by-page fallback.
            rows_payload = []
            seen = set()
            for page in range(200):
                page_params = base_params(page=page, size=1000)
                response = session.get(NSE_RESULTS_API, params=page_params, timeout=60)
                response.raise_for_status()
                payload = response.json()
                items, meta, keys = _extract_result_items(payload)
                diagnostic["PagesFetched"] = page + 1
                if page == 0:
                    diagnostic["PayloadKeys"] = ";".join(map(str, keys[:50]))
                if not items:
                    diagnostic["PaginationStopReason"] = "EMPTY_PAGE"
                    break
                added = 0
                for item in items:
                    stable_id = _first_value(item, ("seq_Id", "seq_id", "seqId", "id"))
                    signature = str(stable_id) if stable_id is not None else "|".join(str(item.get(k, "")) for k in ("symbol", "creation_Date", "qe_Date", "type_Sub", "consolidated", "audited"))
                    if signature not in seen:
                        seen.add(signature)
                        rows_payload.append(item)
                        added += 1
                if added == 0:
                    diagnostic["PaginationStopReason"] = "NO_NEW_RECORDS"
                    break
            else:
                diagnostic["PaginationStopReason"] = "MAX_PAGE_LIMIT_REACHED"
    except Exception as exc:
        diagnostic["Error"] = f"{type(exc).__name__}: {exc}"[:500]
        save_diagnostic()
        raise

    diagnostic["PayloadItemCount"] = len(rows_payload)
    rows = []
    sample_descriptions, sample_matches, sample_matched_keys, sample_matched_fields = [], [], [], []
    for item in rows_payload:
        if not isinstance(item, dict):
            continue
        diagnostic["DictItems"] += 1
        desc = _announcement_description(item)
        if desc:
            diagnostic["DescriptionItems"] += 1
            if len(sample_descriptions) < 5:
                sample_descriptions.append(desc[:240])
        period_end = _announcement_period_end(item, desc)
        symbol = _announcement_symbol(item)
        # This is already the dedicated Integrated Filing-Financials endpoint
        # with `type=Integrated Filing- Financials`; the authoritative row
        # fields are symbol + qe_Date + creation_Date, not announcement text.
        financial_match = bool(symbol and period_end is not None)
        if not financial_match:
            diagnostic["RejectNoFinancialTerm"] += 1
            if period_end is None:
                diagnostic["RejectPeriodMissing"] += 1
            if not symbol:
                diagnostic["RejectSymbolMissing"] += 1
            continue
        diagnostic["FinancialTermMatches"] += 1
        if len(sample_matches) < 8:
            sample_matches.append(desc[:260])
            if len(sample_matched_keys) < 5:
                sample_matched_keys.append(",".join(map(str, list(item.keys())[:100])))
                selected = {str(k): str(v)[:220] for k, v in item.items() if any(token in str(k).lower() for token in (
                    "date", "period", "symbol", "desc", "subject", "name", "detail", "attach", "url", "result", "broadcast", "filing", "relating", "xbrl", "financial", "qe_", "creation", "seq", "type_sub"
                ))}
                sample_matched_fields.append(str(selected)[:1800])
        pub_date = _announcement_date(item)
        if not pub_date or pub_date > end_date or pub_date < start_date:
            diagnostic["RejectDateMissingOrOutOfRange"] += 1
            continue
        diagnostic["PublicationDateParsed"] += 1
        diagnostic["WithinDateRange"] += 1
        diagnostic["SymbolParsed"] += 1
        diagnostic["PeriodEndParsed"] += 1
        attachment = _first_value(item, ("xbrl", "xbrl_Link", "xbrlLink", "xbrl_url", "xbrlUrl", "attchmntFile", "attachment", "attachmentUrl", "attachmentURL", "url", "fileUrl", "file_url", "details", "detailUrl"))
        attachment = str(attachment or "").strip()
        if attachment.startswith("/"):
            attachment = "https://www.nseindia.com" + attachment
        if not attachment.startswith("https://"):
            attachment = ""
        rows.append({
            "TckrSymb": symbol,
            "FinancialPeriodEnd": period_end.isoformat(),
            "PublicationDate": pub_date.isoformat(),
            "PublicationDateStatus": "VERIFIED",
            "FilingDescription": desc,
            "OfficialFilingURL": attachment,
            "OfficialSource": "NSE Integrated Filing - Financials",
            "RetrievedAtUTC": datetime.now(timezone.utc).isoformat(),
        })
    diagnostic["AcceptedRows"] = len(rows)
    diagnostic["SampleDescriptions"] = " || ".join(sample_descriptions)[:1200]
    diagnostic["SampleFinancialResultMatches"] = " || ".join(sample_matches)[:2200]
    diagnostic["SampleMatchedItemKeys"] = " || ".join(sample_matched_keys)[:2400]
    diagnostic["SampleMatchedItemFields"] = " || ".join(sample_matched_fields)[:6000]
    if not rows and not diagnostic["Error"]:
        diagnostic["Error"] = "Integrated Filing API returned records, but none had valid NSE symbol, quarter-end and publication date fields"
    save_diagnostic()
    print(
        "[FUNDAMENTAL OFFICIAL FETCH] "
        f"endpoint=integrated-filing-results homepage={diagnostic['HomepageWarmupStatus']} "
        f"api_status={diagnostic['APIStatusCode']} total_count={diagnostic['ReportedTotalCount']} "
        f"payload_items={diagnostic['PayloadItemCount']} financial_term_matches={diagnostic['FinancialTermMatches']} "
        f"periods_parsed={diagnostic['PeriodEndParsed']} accepted={diagnostic['AcceptedRows']} "
        f"pagination={diagnostic['PaginationStopReason']} diagnostics={diagnostics_path}"
    )
    return pd.DataFrame(rows, columns=[
        "TckrSymb", "FinancialPeriodEnd", "PublicationDate", "PublicationDateStatus",
        "FilingDescription", "OfficialFilingURL", "OfficialSource", "RetrievedAtUTC"
    ])

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
            if not fetched.empty:
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                fetched.to_csv(cache_file, index=False)
                filings = fetched
            else:
                # An empty parsed response can mean NSE changed its schema or
                # the endpoint returned a partial window. Do not erase a useful
                # prior cache; it will be cutoff-filtered below.
                filings = pd.DataFrame()
                diagnostics.append({"Status": "LIVE_FETCH_EMPTY", "Reason": "Live NSE response produced no parseable financial-result filings"})
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
