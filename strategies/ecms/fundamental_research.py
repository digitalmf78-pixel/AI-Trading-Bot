"""Independent, provider-data fundamental research score for ECMS.

This is deliberately NOT the official-filing verifier or production hard gate.
It scores only available numeric inputs, reports coverage, and exposes XBRL
verification as a separate status. Missing inputs reduce coverage and can never
be silently treated as zero. Banks/NBFCs/insurers wait for dedicated sector rules.
"""
from __future__ import annotations

import math
import re
import pandas as pd

METRIC_WEIGHTS = {
    "RevenueGrowthPct": 15.0,
    "ProfitGrowthPct": 15.0,
    "ROEPercent": 12.0,
    "ROCEPercent": 13.0,
    "DebtToEquity": 15.0,
    "InterestCoverage": 10.0,
    "OperatingCashFlowINR": 10.0,
    "FreeCashFlowINR": 5.0,
}
VALUATION_WEIGHT = 10.0
VERIFICATION_METRICS = (
    "RevenueGrowthPct", "ProfitGrowthPct", "ROEPercent", "ROCEPercent",
    "DebtToEquity", "InterestCoverage", "OperatingCashFlowINR",
)
SPECIAL_SECTOR_TERMS = ("bank", "nbfc", "insurance", "insurer", "financial")

ALIGNED_PROVIDER_BASES = {"ANNUAL_ALIGNED_STATEMENTS", "QUARTERLY_TTM_ALIGNED_STATEMENTS"}


def _valid_period(value, metric=None):
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none", "<na>", "latest", "current"}:
        return False
    # Free-source growth rows may carry an explicit consecutive FY range
    # rather than a single date. Accept only adjacent fiscal years.
    if metric in {"RevenueGrowthPct", "ProfitGrowthPct"}:
        match = re.fullmatch(r"FY\s*(20\d{2})\s*->\s*FY\s*(20\d{2})", text, re.IGNORECASE)
        if match:
            return int(match.group(2)) == int(match.group(1)) + 1
    if re.fullmatch(r"FY\s*20\d{2}", text, re.IGNORECASE):
        return True
    if re.fullmatch(r"Q[1-4]\s*FY\s*20\d{2}", text, re.IGNORECASE):
        return True
    parsed = pd.to_datetime(text, errors="coerce", utc=True)
    return not pd.isna(parsed)


def _metric_provenance(row):
    """Return score-eligible metrics and explicit provenance exclusions.

    Yahoo metrics require a verified aligned statement basis. Other named
    providers remain third-party evidence and require their own reported period;
    they are never promoted to official verification by this research layer.
    Legacy rows without per-metric provenance are excluded from scoring.
    """
    import json

    raw = row.get("MetricSourcesJSON")
    try:
        sources = json.loads(str(raw)) if raw is not None and str(raw).strip() else {}
    except (TypeError, ValueError):
        sources = {}
    try:
        periods = json.loads(str(row.get("MetricSourcePeriodsJSON") or "{}"))
    except (TypeError, ValueError):
        periods = {}
    if not isinstance(sources, dict):
        sources = {}
    if not isinstance(periods, dict):
        periods = {}

    basis = str(row.get("MetricCalculationBasis", "") or "").strip().upper()
    alignment = str(row.get("MetricPeriodAlignmentStatus", "") or "").strip().upper()
    try:
        metric_bases = json.loads(str(row.get("MetricCalculationBasesJSON") or "{}"))
    except (TypeError, ValueError):
        metric_bases = {}
    if not isinstance(metric_bases, dict):
        metric_bases = {}
    eligible, blocked = set(), []
    for metric in METRIC_WEIGHTS:
        if _number(row.get(metric)) is None:
            continue
        source = str(sources.get(metric, "") or "").strip()
        period = periods.get(metric, "")
        metric_basis = str(metric_bases.get(metric, basis) or "").strip().upper()
        if not source:
            blocked.append(metric + ":SOURCE_MISSING")
            continue
        source_key = source.lower()
        is_yahoo = "yahoo finance" in source_key or "yfinance" in source_key
        if metric in {"RevenueGrowthPct", "ProfitGrowthPct"} and not is_yahoo:
            # A third-party growth percentage must identify both consecutive
            # fiscal years used in its calculation, not just one as-of date.
            match = re.fullmatch(r"FY\\s*(20\\d{2})\\s*->\\s*FY\\s*(20\\d{2})", str(period or "").strip(), re.IGNORECASE)
            period_valid = bool(match and int(match.group(2)) == int(match.group(1)) + 1)
        else:
            period_valid = _valid_period(period, metric)
        if not period_valid:
            blocked.append(metric + ":PERIOD_MISSING_OR_INVALID")
            continue
        if is_yahoo:
            if metric_basis not in ALIGNED_PROVIDER_BASES or alignment != "VERIFIED":
                blocked.append(metric + ":YAHOO_STATEMENT_ALIGNMENT_NOT_VERIFIED")
                continue
        elif metric_basis != "MULTI_SOURCE_METRIC_LEVEL":
            blocked.append(metric + ":NON_YAHOO_BASIS_NOT_METRIC_LEVEL")
            continue
        eligible.add(metric)
    return eligible, blocked



def _number(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _band(value, bands):
    for minimum, points in bands:
        if value >= minimum:
            return points
    return 0.0


def _metric_points(name, value):
    if name == "RevenueGrowthPct":
        return _band(value, [(25, 15), (15, 12), (8, 9), (0, 6), (-10, 2)])
    if name == "ProfitGrowthPct":
        return _band(value, [(30, 15), (20, 12), (10, 9), (0, 6), (-10, 2)])
    if name == "ROEPercent":
        return _band(value, [(20, 12), (15, 10), (10, 7), (5, 4), (0, 1)])
    if name == "ROCEPercent":
        return _band(value, [(25, 13), (18, 11), (12, 8), (8, 4), (0, 1)])
    if name == "DebtToEquity":
        return 15.0 if value <= 0.3 else 12.0 if value <= 0.7 else 8.0 if value <= 1.2 else 4.0 if value <= 2 else 0.0
    if name == "InterestCoverage":
        return _band(value, [(8, 10), (5, 8), (3, 6), (1.5, 3), (0, 1)])
    if name == "OperatingCashFlowINR":
        return 10.0 if value > 0 else 0.0
    if name == "FreeCashFlowINR":
        return 5.0 if value > 0 else 0.0
    return 0.0


def _valuation_points(row):
    # Valuation figures are point-in-time data; do not score them without a
    # named source and a valid as-of date.
    source = str(row.get("ValuationSource", "") or "").strip()
    as_of = row.get("ValuationAsOfDate", "")
    if not source or not _valid_period(as_of):
        return 0.0, 0.0
    points = 0.0
    available = 0.0
    pe = _number(row.get("TrailingPE"))
    if pe is not None and pe > 0:
        available += 5.0
        points += 5.0 if pe <= 15 else 4.0 if pe <= 25 else 2.0 if pe <= 40 else 0.0
    peg = _number(row.get("PEG"))
    if peg is not None and peg > 0:
        available += 5.0
        points += 5.0 if peg <= 1 else 4.0 if peg <= 1.5 else 2.0 if peg <= 2 else 0.0
    if available == 0:
        pb = _number(row.get("PriceToBook"))
        ev = _number(row.get("EnterpriseToEBITDA"))
        if pb is not None and pb > 0:
            available += 5.0
            points += 5.0 if pb <= 2 else 3.0 if pb <= 4 else 1.0 if pb <= 7 else 0.0
        if ev is not None and ev > 0:
            available += 5.0
            points += 5.0 if ev <= 8 else 3.0 if ev <= 12 else 1.0 if ev <= 20 else 0.0
    return points, available


def _verification_summary(verification):
    if verification is None or verification.empty or "MetricName" not in verification:
        return "NOT_VERIFIED", 0, len(VERIFICATION_METRICS)
    rows = verification[verification["MetricName"].astype(str).isin(VERIFICATION_METRICS)].copy()
    status_col = "MetricValueVerificationStatus"
    if status_col not in rows:
        return "NOT_VERIFIED", 0, len(VERIFICATION_METRICS)
    verified = set(rows.loc[
        rows[status_col].astype(str).str.upper().eq("OFFICIAL_XBRL_VERIFIED"), "MetricName"
    ])
    count = len(verified)
    if count == len(VERIFICATION_METRICS):
        status = "FULLY_VERIFIED"
    elif count:
        status = "PARTIALLY_VERIFIED"
    else:
        status = "NOT_VERIFIED"
    return status, count, len(VERIFICATION_METRICS)


def assess_fundamental_research(frame, metric_verification=None):
    """Add independent score, data coverage, classification and verification status."""
    result = frame.copy()
    verification = metric_verification if metric_verification is not None else pd.DataFrame()
    verification_by_symbol = {}
    if not verification.empty and {"TckrSymb", "MetricName"}.issubset(verification.columns):
        for symbol, rows in verification.groupby(verification["TckrSymb"].astype(str).str.upper()):
            verification_by_symbol[symbol] = rows

    scores, coverages, classifications, verification_statuses = [], [], [], []
    verified_counts, verification_counts, notes = [], [], []
    for _, row in result.iterrows():
        sector = str(row.get("ProviderSector", "") or "").strip().lower()
        if any(term in sector for term in SPECIAL_SECTOR_TERMS):
            scores.append(pd.NA)
            coverages.append(0.0)
            classifications.append("INSUFFICIENT_DATA")
            notes.append("SECTOR_SPECIFIC_RULES_REQUIRED:NIM_GNPA_CAR")
        else:
            earned = 0.0
            available = 0.0
            eligible_metrics, blocked_metrics = _metric_provenance(row)
            for metric, weight in METRIC_WEIGHTS.items():
                value = _number(row.get(metric))
                if value is None or metric not in eligible_metrics:
                    continue
                available += weight
                earned += _metric_points(metric, value)
            valuation_points, valuation_available = _valuation_points(row)
            available += valuation_available
            earned += valuation_points
            coverage = available / 105.0 * 100.0
            score = (earned / available * 100.0) if available else None
            if coverage < 60 or score is None:
                classification = "INSUFFICIENT_DATA"
            elif coverage >= 80 and score >= 75:
                classification = "STRONG"
            elif coverage >= 65 and score >= 60:
                classification = "GOOD"
            elif score >= 45:
                classification = "AVERAGE"
            else:
                classification = "WEAK"
            # Do not publish a numeric research score when metric coverage
            # is below the minimum evidence threshold.
            publishable_score = score if coverage >= 60 else None
            scores.append(round(publishable_score, 2) if publishable_score is not None else pd.NA)
            coverages.append(round(coverage, 2))
            classifications.append(classification)
            missing = [m for m in (*METRIC_WEIGHTS, "TrailingPE/PEG-or-PB/EV") if (
                m == "TrailingPE/PEG-or-PB/EV" and valuation_available == 0
            ) or (m != "TrailingPE/PEG-or-PB/EV" and _number(row.get(m)) is None)]
            blocked = sorted(set(blocked_metrics))
            note_parts = []
            if missing:
                note_parts.append("MISSING_INPUTS:" + ",".join(missing))
            if blocked:
                note_parts.append("PROVENANCE_BLOCKED:" + ",".join(blocked))
            notes.append(";".join(note_parts) if note_parts else "AVAILABLE_INPUTS_SCORED")

        symbol = str(row.get("TckrSymb", "")).strip().upper()
        status, count, total = _verification_summary(verification_by_symbol.get(symbol, pd.DataFrame()))
        verification_statuses.append(status)
        verified_counts.append(count)
        verification_counts.append(total)

    result["FundamentalResearchScore"] = scores
    result["FundamentalResearchCoveragePct"] = coverages
    result["FundamentalResearchClassification"] = classifications
    result["FundamentalVerificationStatus"] = verification_statuses
    result["FundamentalVerifiedMetricCount"] = verified_counts
    result["FundamentalVerificationMetricCount"] = verification_counts
    result["FundamentalResearchNotes"] = notes
    result["FundamentalResearchEligibleMetricCount"] = [
        len(_metric_provenance(row)[0]) for _, row in result.iterrows()
    ]
    result["FundamentalResearchProvenanceStatus"] = [
        "PROVENANCE_OK" if not _metric_provenance(row)[1] else
        "PARTIAL_OR_BLOCKED" if _metric_provenance(row)[0] else "NO_ELIGIBLE_METRICS"
        for _, row in result.iterrows()
    ]
    return result
