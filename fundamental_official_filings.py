"""Point-in-time verification of NSE financial-results publication dates.

Only a matching NSE corporate-announcement record whose description explicitly
contains the financial period end is accepted as publication-date evidence.
This module does not invent dates and does not remove candidate stocks.
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
    parsed = pd.to_datetime(value, errors="coerce", dayfirst=True)
    return None if pd.isna(parsed) else parsed.date()


def _period_end_from_description(description: str):
    """Extract an explicitly mentioned period-end date from common NSE wording."""
    text = str(description or "")
    # Common forms: 30-Jun-2026, 30/06/2026, June 30, 2026, 30 June 2026.
    patterns = [
        r"\b(\d{1,2}[-/]\d{1,2}[-/]\d{4})\b",
        r"\b(\d{1,2}[- ][A-Za-z]{3,9}[- ,]+\d{4})\b",
        r"\b([A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})\b",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            d = _date(match.group(1))
            if d:
                return d
    return None


def _announcement_date(item: dict):
    for key in ("an_dt", "announcementDate", "date", "sort_date", "timestamp"):
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


def fetch_nse_financial_results(asof_date, lookback_days: int = 400, session_factory=None):
    """Fetch NSE official announcements through EOD date. Raises on access errors."""
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
    })
    home = session.get(NSE_HOME, timeout=20)
    home.raise_for_status()
    params = {
        "index": "equities",
        "from_date": start_date.strftime("%d-%m-%Y"),
        "to_date": end_date.strftime("%d-%m-%Y"),
    }
    response = session.get(NSE_API, params=params, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict):
        for key in ("data", "rows", "announcements"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
    if not isinstance(payload, list):
        raise ValueError("Unexpected NSE corporate-announcements response schema")

    rows = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        desc = _announcement_description(item)
        lower = desc.lower()
        if not any(term in lower for term in ("financial results", "financial result", "unaudited results", "audited results")):
            continue
        pub_date = _announcement_date(item)
        if not pub_date or pub_date > end_date or pub_date < start_date:
            continue
        symbol = _announcement_symbol(item)
        period_end = _period_end_from_description(desc)
        if not symbol or not period_end:
            continue
        attachment = str(item.get("attchmntFile", item.get("attachment", item.get("url", ""))) or "").strip()
        if attachment and attachment.startswith("/"):
            attachment = "https://www.nseindia.com" + attachment
        if not attachment.startswith("https://"):
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
        })
    return pd.DataFrame(rows, columns=[
        "TckrSymb", "FinancialPeriodEnd", "PublicationDate", "PublicationDateStatus",
        "FilingDescription", "OfficialFilingURL", "OfficialSource", "RetrievedAtUTC",
    ])


def apply_official_publication_dates(records: pd.DataFrame, asof_date, filings: pd.DataFrame | None = None,
                                    fetcher: Callable | None = None, cache_path=FILINGS_CACHE,
                                    diagnostics_path=VERIFY_DIAGNOSTICS):
    """Verify publication dates only for exact symbol + period-end matches.

    Retrieval failures are non-fatal. Existing candidate rows and metric values
    are preserved; unverified dates remain unverified.
    """
    output = records.copy()
    if "TckrSymb" not in output:
        output["TckrSymb"] = ""
    for col, default in (("PublicationDate", pd.NA), ("PublicationDateStatus", "UNVERIFIED"),
                         ("OfficialFilingURL", pd.NA), ("OfficialFilingSource", pd.NA)):
        if col not in output:
            output[col] = default
    cutoff = pd.to_datetime(asof_date, errors="coerce")
    diagnostics = []
    if filings is None:
        try:
            fetch = fetcher or fetch_nse_financial_results
            filings = fetch(asof_date)
            Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
            filings.to_csv(cache_path, index=False)
        except Exception as exc:
            diagnostics.append({"Status": "FETCH_FAILED", "Reason": f"{type(exc).__name__}: {exc}"[:500]})
            filings = pd.DataFrame()
    if filings is None or filings.empty:
        diagnostics.append({"Status": "NO_MATCHING_OFFICIAL_FILINGS", "Reason": "No official NSE results filing could be matched; dates remain UNVERIFIED"})
        Path(diagnostics_path).parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(diagnostics).to_csv(diagnostics_path, index=False)
        return output

    filings = filings.copy()
    for col in ("TckrSymb", "FinancialPeriodEnd", "PublicationDate", "PublicationDateStatus", "OfficialFilingURL", "OfficialSource"):
        if col not in filings:
            filings[col] = pd.NA
    filings["TckrSymb"] = filings["TckrSymb"].astype(str).str.strip().str.upper()
    filings["FinancialPeriodEndParsed"] = pd.to_datetime(filings["FinancialPeriodEnd"], errors="coerce").dt.normalize()
    filings["PublicationDateParsed"] = pd.to_datetime(filings["PublicationDate"], errors="coerce").dt.normalize()
    verified = filings[filings["PublicationDateStatus"].astype(str).str.upper().eq("VERIFIED")].copy()
    if pd.notna(cutoff):
        verified = verified[verified["PublicationDateParsed"].notna() & verified["PublicationDateParsed"].le(cutoff.normalize())]
    verified = verified.dropna(subset=["FinancialPeriodEndParsed", "PublicationDateParsed"])
    # Keep latest publication date for exact symbol + period, without crossing EOD.
    verified = verified.sort_values("PublicationDateParsed").drop_duplicates(["TckrSymb", "FinancialPeriodEndParsed"], keep="last")
    index = {(r["TckrSymb"], r["FinancialPeriodEndParsed"]): r for _, r in verified.iterrows()}

    matched = 0
    for idx, row in output.iterrows():
        symbol = str(row.get("TckrSymb", "")).strip().upper()
        period = pd.to_datetime(row.get("FinancialPeriodEnd", row.get("AsOfDate", pd.NA)), errors="coerce")
        if not symbol or pd.isna(period):
            diagnostics.append({"TckrSymb": symbol, "Status": "UNMATCHED", "Reason": "Missing symbol or financial period end"})
            continue
        filing = index.get((symbol, period.normalize()))
        if filing is None:
            diagnostics.append({"TckrSymb": symbol, "FinancialPeriodEnd": period.date().isoformat(), "Status": "UNVERIFIED", "Reason": "No exact official symbol + period-end match"})
            continue
        pub = filing["PublicationDateParsed"]
        if pd.notna(cutoff) and pub > cutoff.normalize():
            diagnostics.append({"TckrSymb": symbol, "Status": "UNVERIFIED", "Reason": "Official filing published after EOD"})
            continue
        output.at[idx, "PublicationDate"] = pub.date().isoformat()
        output.at[idx, "PublicationDateStatus"] = "VERIFIED"
        output.at[idx, "OfficialFilingURL"] = filing.get("OfficialFilingURL", NSE_FILINGS_PAGE)
        output.at[idx, "OfficialFilingSource"] = filing.get("OfficialSource", "NSE corporate announcements")
        matched += 1
        diagnostics.append({"TckrSymb": symbol, "FinancialPeriodEnd": period.date().isoformat(), "PublicationDate": pub.date().isoformat(), "Status": "VERIFIED", "OfficialFilingURL": output.at[idx, "OfficialFilingURL"]})
    Path(diagnostics_path).parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(diagnostics).to_csv(diagnostics_path, index=False)
    print(f"[FUNDAMENTAL OFFICIAL DATE] verified={matched}; candidates={len(output)}; unmatched remain UNVERIFIED")
    return output
