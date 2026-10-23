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
    # Prefer unambiguous ISO dates before trying common NSE day-first formats.
    parsed = pd.to_datetime(value, errors="coerce", format="%Y-%m-%d")
    if pd.isna(parsed):
        parsed = pd.to_datetime(value, errors="coerce", dayfirst=True)
    return None if pd.isna(parsed) else parsed.date()


def _period_end_from_description(description: str):
    """Extract only dates explicitly tied to a financial period end.

    This deliberately avoids taking the first arbitrary date in an announcement,
    which could be a board-meeting date rather than the statement period end.
    """
    text = str(description or "")
    patterns = [
        r"(?:period|quarter|year|nine months|half year)\s+ended\s+(\d{1,2}[-/]\d{1,2}[-/]\d{4})",
        r"(?:period|quarter|year|nine months|half year)\s+ended\s+(\d{1,2}[- ][A-Za-z]{3,9}[- ,]+\d{4})",
        r"(?:period|quarter|year|nine months|half year)\s+ended\s+([A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            parsed = _date(match.group(1))
            if parsed:
                return parsed
    return None


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


def fetch_nse_financial_results(asof_date, lookback_days: int = 450, session_factory=None):
    """Fetch NSE corporate announcements through the requested EOD date."""
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
    params = {"index": "equities", "from_date": start_date.strftime("%d-%m-%Y"), "to_date": end_date.strftime("%d-%m-%Y")}
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
        if not any(term in lower for term in ("financial results", "financial result", "unaudited results", "audited results", "integrated filing - financial")):
            continue
        pub_date = _announcement_date(item)
        if not pub_date or pub_date > end_date or pub_date < start_date:
            continue
        symbol = _announcement_symbol(item)
        period_end = _announcement_period_end(item, desc)
        if not symbol or not period_end:
            continue
        attachment = str(item.get("attchmntFile", item.get("attachment", item.get("url", ""))) or "").strip()
        if attachment.startswith("/"):
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
    return pd.DataFrame(rows, columns=["TckrSymb", "FinancialPeriodEnd", "PublicationDate", "PublicationDateStatus", "FilingDescription", "OfficialFilingURL", "OfficialSource", "RetrievedAtUTC"])


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
    if filings is None:
        try:
            filings = (fetcher or fetch_nse_financial_results)(cutoff.date().isoformat())
            Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
            filings.to_csv(cache_path, index=False)
        except Exception as exc:
            diagnostics.append({"Status": "FETCH_FAILED", "Reason": f"{type(exc).__name__}: {exc}"[:500]})
            filings = pd.DataFrame()
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
