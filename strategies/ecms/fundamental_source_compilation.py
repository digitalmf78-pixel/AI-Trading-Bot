"""ECMS-only compilation of metric observations from independent sources.

This module does not fetch or scrape Screener.in. Free Screener and BSE observations
may be supplied through an explicit, user-maintained CSV. Third-party observations
never become official-XBRL verification merely by appearing in this report.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

METRICS = (
    "RevenueGrowthPct", "ProfitGrowthPct", "ROEPercent", "ROCEPercent",
    "DebtToEquity", "InterestCoverage", "OperatingCashFlowINR",
)
JSON_FIELDS = {
    "source": "MetricSourcesJSON",
    "url": "MetricSourceURLsJSON",
    "period": "MetricSourcePeriodsJSON",
    "basis": "MetricCalculationBasesJSON",
    "currency": "MetricSourceCurrenciesJSON",
}
MANUAL_COLUMNS = [
    "TckrSymb", "MetricName", "MetricValue", "Source", "SourceURL",
    "FinancialPeriodEnd", "PublicationDate", "CalculationBasis", "Unit",
    "ObservationNotes",
]
OUTPUT_COLUMNS = [
    "TckrSymb", "MetricName", "MetricValue", "Source", "SourceURL",
    "FinancialPeriodEnd", "PublicationDate", "CalculationBasis", "Unit",
    "SourceStatus", "VerificationStatus", "MismatchStatus", "MismatchReason",
    "ObservationNotes",
]


def _mapping(value):
    try:
        parsed = json.loads(str(value)) if value is not None and str(value).strip() else {}
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def empty_manual_observation_template() -> pd.DataFrame:
    """Return the header-only schema for manually captured BSE/Screener observations."""
    return pd.DataFrame(columns=MANUAL_COLUMNS)


def _provider_rows(metrics: pd.DataFrame) -> list[dict]:
    rows = []
    for _, item in metrics.iterrows():
        symbol = str(item.get("TckrSymb", "") or "").strip().upper()
        if not symbol:
            continue
        maps = {name: _mapping(item.get(column)) for name, column in JSON_FIELDS.items()}
        for metric in METRICS:
            value = _number(item.get(metric))
            if value is None:
                continue
            source = str(maps["source"].get(metric, "") or "").strip()
            rows.append({
                "TckrSymb": symbol,
                "MetricName": metric,
                "MetricValue": value,
                "Source": source or "PROVIDER_SOURCE_UNSPECIFIED",
                "SourceURL": str(maps["url"].get(metric, "") or "").strip(),
                "FinancialPeriodEnd": str(maps["period"].get(metric, "") or "").strip(),
                "PublicationDate": str(item.get("PublicationDate", "") or "").strip(),
                "CalculationBasis": str(maps["basis"].get(metric, item.get("MetricCalculationBasis", "")) or "").strip(),
                "Unit": str(maps["currency"].get(metric, "PERCENT" if metric.endswith("Pct") else "RATIO" if metric in {"DebtToEquity", "InterestCoverage"} else "INR") or "").strip(),
                "SourceStatus": "OBSERVATION_ONLY",
                "VerificationStatus": "NOT_OFFICIALLY_VERIFIED",
                "MismatchStatus": "NOT_ASSESSED",
                "MismatchReason": "",
                "ObservationNotes": "Provider metric; retain its metric-level provenance",
            })
    return rows


def _verification_rows(verification: pd.DataFrame) -> list[dict]:
    rows = []
    if verification is None or verification.empty:
        return rows
    for _, item in verification.iterrows():
        metric = str(item.get("MetricName", "") or "").strip()
        symbol = str(item.get("TckrSymb", "") or "").strip().upper()
        if not symbol or metric not in METRICS:
            continue
        status = str(item.get("MetricValueVerificationStatus", "") or "").strip().upper()
        rows.append({
            "TckrSymb": symbol,
            "MetricName": metric,
            "MetricValue": _number(item.get("OfficialMetricValue", item.get("ProviderMetricValue"))),
            "Source": "NSE_OFFICIAL_XBRL_AUDIT",
            "SourceURL": str(item.get("OfficialFilingURL", item.get("EvidenceFilePath", "")) or "").strip(),
            "FinancialPeriodEnd": str(item.get("FinancialPeriodEnd", "") or "").strip(),
            "PublicationDate": str(item.get("PublicationDate", "") or "").strip(),
            "CalculationBasis": str(item.get("MetricCalculationBasis", item.get("VerificationMethod", "")) or "").strip(),
            "Unit": str(item.get("Unit", "") or "").strip(),
            "SourceStatus": "OFFICIAL_AUDIT_RESULT",
            "VerificationStatus": status or "UNVERIFIED",
            "MismatchStatus": "MISMATCH" if "MISMATCH" in status else "NOT_ASSESSED",
            "MismatchReason": str(item.get("VerificationReason", "") or "").strip(),
            "ObservationNotes": "Official status is carried through unchanged from the XBRL audit",
        })
    return rows


def _manual_rows(observations: pd.DataFrame) -> list[dict]:
    rows = []
    if observations is None or observations.empty:
        return rows
    missing = set(MANUAL_COLUMNS) - set(observations.columns)
    if missing:
        raise ValueError("Manual observation schema missing columns: " + ", ".join(sorted(missing)))
    for _, item in observations.iterrows():
        symbol = str(item.get("TckrSymb", "") or "").strip().upper()
        metric = str(item.get("MetricName", "") or "").strip()
        source = str(item.get("Source", "") or "").strip().upper()
        if not symbol or metric not in METRICS:
            continue
        if source not in {"SCREENER_FREE_MANUAL", "BSE_OFFICIAL_FILING_MANUAL"}:
            raise ValueError("Manual Source must be SCREENER_FREE_MANUAL or BSE_OFFICIAL_FILING_MANUAL")
        rows.append({
            "TckrSymb": symbol,
            "MetricName": metric,
            "MetricValue": _number(item.get("MetricValue")),
            "Source": source,
            "SourceURL": str(item.get("SourceURL", "") or "").strip(),
            "FinancialPeriodEnd": str(item.get("FinancialPeriodEnd", "") or "").strip(),
            "PublicationDate": str(item.get("PublicationDate", "") or "").strip(),
            "CalculationBasis": str(item.get("CalculationBasis", "") or "").strip(),
            "Unit": str(item.get("Unit", "") or "").strip(),
            "SourceStatus": "MANUAL_OBSERVATION_ONLY",
            "VerificationStatus": "NOT_OFFICIALLY_VERIFIED",
            "MismatchStatus": "NOT_ASSESSED",
            "MismatchReason": "",
            "ObservationNotes": str(item.get("ObservationNotes", "") or "").strip(),
        })
    return rows


def build_fundamental_source_compilation(
    metrics: pd.DataFrame,
    verification: pd.DataFrame | None = None,
    manual_observations: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Compile provider, official NSE audit, and manual BSE/Screener observations.

    Sources remain separate rows; values are never averaged or silently reconciled.
    Manual BSE/Screener rows are always observation-only and cannot satisfy the
    strict official-XBRL gate.
    """
    if metrics is None or "TckrSymb" not in metrics.columns:
        raise ValueError("Metrics input must contain TckrSymb")
    rows = _provider_rows(metrics)
    rows.extend(_verification_rows(verification if verification is not None else pd.DataFrame()))
    rows.extend(_manual_rows(manual_observations if manual_observations is not None else pd.DataFrame()))\n    rows.extend(_debt_equity_rows(debt_equity_audit))
    if not rows:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    result = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    result["TckrSymb"] = result["TckrSymb"].astype(str).str.strip().str.upper()
    result["MetricName"] = result["MetricName"].astype(str).str.strip()
    return result.sort_values(["TckrSymb", "MetricName", "Source", "FinancialPeriodEnd"], kind="stable").reset_index(drop=True)


def write_fundamental_source_compilation(
    metrics_path: str | Path,
    output_path: str | Path,
    verification_path: str | Path | None = None,
    manual_observations_path: str | Path | None = None,
) -> pd.DataFrame:
    metrics = pd.read_csv(metrics_path, keep_default_na=False)
    verification = (
        pd.read_csv(verification_path, keep_default_na=False)
        if verification_path and Path(verification_path).is_file() else pd.DataFrame()
    )
    manual = (
        pd.read_csv(manual_observations_path, keep_default_na=False)
        if manual_observations_path and Path(manual_observations_path).is_file() else pd.DataFrame()
    )
    result = build_fundamental_source_compilation(metrics, verification, manual, debt_equity_audit)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(destination, index=False)
    return result
