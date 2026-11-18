"""Read-only reconciliation of announced NSE results events with official filings.

This module produces diagnostics only. It never changes the Results Universe,
candidate eligibility, Delivery/RVOL/Liquidity rules, caches, or workflow timing.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
import re

import pandas as pd


def _as_date(value):
    if value is None or str(value).strip().lower() in {"", "nan", "none", "nat"}:
        return None
    parsed = pd.to_datetime(value, errors="coerce", dayfirst=not bool(re.match(r"^\d{4}-\d{2}-\d{2}$", str(value).strip())))
    return None if pd.isna(parsed) else parsed.date()


def _expected_period_end(purpose: str, details: str):
    """Only return a period end explicitly present in NSE event text."""
    text = f"{purpose or ''} {details or ''}".strip()
    if not text:
        return None
    try:
        from fundamental_official_filings import _period_end_from_description
        value = _period_end_from_description(text)
        if value is not None and not pd.isna(value):
            return value.date() if hasattr(value, "date") else value
    except Exception:
        # Missing/unsupported event wording remains unclassified; never infer a quarter.
        pass
    return None


def build_results_verification_report(
    results_audit: pd.DataFrame,
    filings: pd.DataFrame,
    as_of_date: date,
) -> pd.DataFrame:
    """Reconcile announced result events against filing snapshot, without gating stocks.

    Exact period matches can be labelled filed. If event text omits an explicit
    period end, prior filings are flagged for manual period confirmation only.
    """
    columns = [
        "TckrSymb", "BoardMeetingDate", "ResultsPurpose", "ResultsDetails",
        "ExpectedFinancialPeriodEnd", "MeetingStatus", "FilingVerificationStatus",
        "LatestPriorFinancialPeriodEnd", "LatestPriorFilingDate",
        "ExactPeriodFilingDate", "ExactPeriodFilingURL", "FilingRowsForSymbol",
        "AsOfDate", "ResultsCalendarSourceURL", "FilingSource",
    ]
    if results_audit is None or results_audit.empty:
        return pd.DataFrame(columns=columns)

    audit = results_audit.copy()
    if "ResultsUniverseStatus" in audit:
        audit = audit[audit["ResultsUniverseStatus"].astype(str).str.startswith("PASS")].copy()
    if audit.empty:
        return pd.DataFrame(columns=columns)

    filing_frame = filings.copy() if isinstance(filings, pd.DataFrame) else pd.DataFrame()
    required = {"TckrSymb", "FinancialPeriodEnd", "PublicationDate"}
    filing_snapshot_valid = not filing_frame.empty and required.issubset(filing_frame.columns)
    if filing_snapshot_valid:
        filing_frame["TckrSymb"] = filing_frame["TckrSymb"].astype(str).str.strip().str.upper()
        filing_frame["_period"] = filing_frame["FinancialPeriodEnd"].map(_as_date)
        filing_frame["_publication"] = filing_frame["PublicationDate"].map(_as_date)
        filing_frame = filing_frame[
            filing_frame["_period"].notna()
            & filing_frame["_publication"].notna()
            & filing_frame["_publication"].le(as_of_date)
        ].copy()
        if "PublicationDateStatus" in filing_frame:
            filing_frame = filing_frame[
                filing_frame["PublicationDateStatus"].astype(str).str.upper().eq("VERIFIED")
            ].copy()

    rows = []
    for event in audit.to_dict("records"):
        symbol = str(event.get("TckrSymb", "") or "").strip().upper()
        meeting_date = _as_date(event.get("OfficialResultsDate"))
        purpose = str(event.get("ResultsPurpose", "") or "")
        details = str(event.get("ResultsDetails", "") or "")
        event_text = f"{purpose} {details}".strip()
        expected_period = _expected_period_end(purpose, details)
        if re.search(r"\bcancel(?:led|ed)\b|withdrawn", event_text, re.I):
            meeting_status = "CANCELLED_EVIDENCE_IN_CALENDAR_TEXT"
        elif re.search(r"\bpostponed\b", event_text, re.I):
            meeting_status = "POSTPONED_REVIEW"
        elif re.search(r"\brescheduled\b|\breschedule\b", event_text, re.I):
            meeting_status = "RESCHEDULED_REVIEW"
        else:
            meeting_status = "SCHEDULED_AS_PER_NSE_CALENDAR"

        symbol_filings = (
            filing_frame[filing_frame["TckrSymb"].eq(symbol)].sort_values(
                ["_publication", "_period"], ascending=[False, False]
            ) if filing_snapshot_valid else pd.DataFrame()
        )
        latest = symbol_filings.iloc[0] if not symbol_filings.empty else None
        exact = (
            symbol_filings[symbol_filings["_period"].eq(expected_period)]
            if expected_period is not None and not symbol_filings.empty
            else pd.DataFrame()
        )
        if not filing_snapshot_valid:
            filing_status = "WAIT_FOR_DATA_NO_VALID_FILING_SNAPSHOT"
        elif expected_period is not None and not exact.empty:
            filing_status = "RESULTS_FILED_FOR_EXPLICIT_EVENT_PERIOD"
        elif expected_period is not None:
            filing_status = "NO_MATCHING_FILING_FOR_EXPLICIT_EVENT_PERIOD"
        elif not symbol_filings.empty:
            filing_status = "PRIOR_FILING_REQUIRES_PERIOD_CONFIRMATION"
        else:
            filing_status = "NO_PRIOR_FILING_FOUND_IN_AVAILABLE_SNAPSHOT"

        exact_row = exact.sort_values("_publication").iloc[-1] if not exact.empty else None
        rows.append({
            "TckrSymb": symbol,
            "BoardMeetingDate": meeting_date.isoformat() if meeting_date else "",
            "ResultsPurpose": purpose,
            "ResultsDetails": details,
            "ExpectedFinancialPeriodEnd": expected_period.isoformat() if expected_period else "",
            "MeetingStatus": meeting_status,
            "FilingVerificationStatus": filing_status,
            "LatestPriorFinancialPeriodEnd": latest["_period"].isoformat() if latest is not None else "",
            "LatestPriorFilingDate": latest["_publication"].isoformat() if latest is not None else "",
            "ExactPeriodFilingDate": exact_row["_publication"].isoformat() if exact_row is not None else "",
            "ExactPeriodFilingURL": str(exact_row.get("OfficialFilingURL", "") or "") if exact_row is not None else "",
            "FilingRowsForSymbol": int(len(symbol_filings)),
            "AsOfDate": as_of_date.isoformat(),
            "ResultsCalendarSourceURL": str(event.get("ResultsSourceURL", "") or ""),
            "FilingSource": "NSE Integrated Filing - Financials" if filing_snapshot_valid else "NOT_AVAILABLE",
        })
    return pd.DataFrame(rows, columns=columns)


def write_results_verification_report(
    results_audit: pd.DataFrame,
    as_of_date: date,
    filings_path="outputs/v8_official_financial_results_filings.csv",
    output_dir="outputs",
) -> pd.DataFrame:
    """Write the independent verification report; errors must not gate the scanner."""
    path = Path(filings_path)
    filings = pd.read_csv(path) if path.exists() else pd.DataFrame()
    report = build_results_verification_report(results_audit, filings, as_of_date)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    stamp = as_of_date.strftime("%Y%m%d")
    report.to_csv(out / f"v8_results_verification_audit_{stamp}.csv", index=False)
    counts = report["FilingVerificationStatus"].value_counts().to_dict() if not report.empty else {}
    print(
        "[RESULTS VERIFICATION] "
        f"events={len(report)} "
        f"filed_exact_period={counts.get('RESULTS_FILED_FOR_EXPLICIT_EVENT_PERIOD', 0)} "
        f"period_review={counts.get('PRIOR_FILING_REQUIRES_PERIOD_CONFIRMATION', 0)} "
        f"no_prior_filing={counts.get('NO_PRIOR_FILING_FOUND_IN_AVAILABLE_SNAPSHOT', 0)} "
        f"wait_for_data={counts.get('WAIT_FOR_DATA_NO_VALID_FILING_SNAPSHOT', 0)} "
        "selection_gate=UNCHANGED"
    )
    return report



def refresh_official_results_filings(as_of_date: date, filings_path="outputs/v8_official_financial_results_filings.csv"):
    """Fetch a fresh NSE Integrated Filing snapshot; never trust a stale cache."""
    from fundamental_official_filings import fetch_nse_financial_results

    fresh = fetch_nse_financial_results(as_of_date, lookback_days=730)
    required = {"TckrSymb", "FinancialPeriodEnd", "PublicationDate", "PublicationDateStatus"}
    if fresh is None or fresh.empty or not required.issubset(fresh.columns):
        raise RuntimeError("NSE Integrated Filing refresh returned an empty or invalid snapshot")
    fresh = fresh.copy()
    fresh["TckrSymb"] = fresh["TckrSymb"].astype(str).str.strip().str.upper()
    fresh["_period"] = fresh["FinancialPeriodEnd"].map(_as_date)
    fresh["_publication"] = fresh["PublicationDate"].map(_as_date)
    fresh = fresh[
        fresh["TckrSymb"].ne("")
        & fresh["_period"].notna()
        & fresh["_publication"].notna()
        & fresh["_publication"].le(as_of_date)
        & fresh["PublicationDateStatus"].astype(str).str.upper().eq("VERIFIED")
    ].copy()
    if fresh.empty:
        raise RuntimeError("NSE Integrated Filing refresh contained no valid VERIFIED filing rows")
    fresh = fresh.drop(columns=["_period", "_publication"])
    path = Path(filings_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    fresh.to_csv(temp_path, index=False)
    temp_path.replace(path)
    print(f"[RESULTS VERIFICATION] Fresh NSE filing snapshot: rows={len(fresh)} path={path}")
    return fresh


def apply_past_month_results_filing_gate(candidates: pd.DataFrame, results_audit: pd.DataFrame,
                                         as_of_date: date, filings_path="outputs/v8_official_financial_results_filings.csv"):
    """Require an exact-period VERIFIED NSE filing for previous-calendar-month events."""
    if candidates is None or candidates.empty:
        return candidates.copy() if isinstance(candidates, pd.DataFrame) else pd.DataFrame(), results_audit
    audit = results_audit.copy() if isinstance(results_audit, pd.DataFrame) else pd.DataFrame()
    last_year, last_month = (as_of_date.year - 1, 12) if as_of_date.month == 1 else (as_of_date.year, as_of_date.month - 1)
    last_start = date(last_year, last_month, 1)
    last_end = as_of_date - pd.Timedelta(days=as_of_date.day)
    event_dates = audit.get("OfficialResultsDate", pd.Series("", index=audit.index)).map(_as_date)
    past_mask = event_dates.map(lambda value: value is not None and last_start <= value <= last_end)
    past_symbols = set(audit.loc[past_mask, "TckrSymb"].astype(str).str.strip().str.upper())
    if not past_symbols:
        audit["ResultsFilingGateStatus"] = "NOT_REQUIRED_UPCOMING_EVENT"
        return candidates.copy(), audit

    try:
        filings = refresh_official_results_filings(as_of_date, filings_path=filings_path)
        filing_frame = filings.copy()
        filing_frame["_period"] = filing_frame["FinancialPeriodEnd"].map(_as_date)
        filing_frame["_publication"] = filing_frame["PublicationDate"].map(_as_date)
        verified_rows = filing_frame[
            filing_frame["PublicationDateStatus"].astype(str).str.upper().eq("VERIFIED")
            & filing_frame["_period"].notna()
            & filing_frame["_publication"].notna()
            & filing_frame["_publication"].le(as_of_date)
        ]
        refresh_error = ""
    except Exception as exc:
        verified_rows = pd.DataFrame()
        refresh_error = f"{type(exc).__name__}: {exc}"

    statuses = {}
    for _, event in audit.loc[past_mask].iterrows():
        symbol = str(event.get("TckrSymb", "")).strip().upper()
        expected = _expected_period_end(str(event.get("ResultsPurpose", "")), str(event.get("ResultsDetails", "")))
        if refresh_error:
            status = "WAIT_FOR_DATA_FILING_REFRESH_FAILED"
        elif expected is None:
            status = "WAIT_FOR_DATA_EVENT_PERIOD_NOT_EXPLICIT"
        else:
            exact = verified_rows[
                verified_rows["TckrSymb"].astype(str).str.strip().str.upper().eq(symbol)
                & verified_rows["_period"].eq(expected)
            ]
            status = "PASS_EXACT_PERIOD_NSE_FILING_VERIFIED" if not exact.empty else "WAIT_FOR_DATA_NO_EXACT_PERIOD_NSE_FILING"
        statuses[symbol] = status

    if "TckrSymb" in audit.columns:
        audit["ResultsFilingGateStatus"] = [
            statuses.get(str(symbol).strip().upper(), "NOT_REQUIRED_UPCOMING_EVENT")
            for symbol in audit["TckrSymb"]
        ]
    allowed = {symbol for symbol, status in statuses.items() if status == "PASS_EXACT_PERIOD_NSE_FILING_VERIFIED"}
    keep_symbols = (set(candidates["TckrSymb"].astype(str).str.strip().str.upper()) - past_symbols) | allowed
    gated = candidates[candidates["TckrSymb"].astype(str).str.strip().str.upper().isin(keep_symbols)].copy()
    print(f"[RESULTS FILING GATE] past_month={len(past_symbols)} verified={len(allowed)} wait={len(past_symbols)-len(allowed)} refresh_error={bool(refresh_error)}")
    return gated, audit

