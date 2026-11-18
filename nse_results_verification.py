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
    parsed = pd.to_datetime(value, errors="coerce", dayfirst=not bool(re.match(r"^\\d{4}-\\d{2}-\\d{2}$", str(value).strip())))
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
        if re.search(r"\\bcancel(?:led|ed)\\b|withdrawn", event_text, re.I):
            meeting_status = "CANCELLED_EVIDENCE_IN_CALENDAR_TEXT"
        elif re.search(r"\\bpostponed\\b", event_text, re.I):
            meeting_status = "POSTPONED_REVIEW"
        elif re.search(r"\\brescheduled\\b|\\breschedule\\b", event_text, re.I):
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
