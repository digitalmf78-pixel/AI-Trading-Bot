"""ECMS-only, fail-closed Debt/Equity reconciliation against official NSE XBRL.

This module is deliberately not wired into the shared V8 verifier or ECMS
shortlist. It produces a separate diagnostic/audit frame for review first.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

import pandas as pd

from fundamental_metric_verification import (
    _clean,
    _fact_value,
    _filing_metadata_status,
    _filing_reporting_basis,
    _local,
    _metric_source,
    _namespace,
    _number,
    _parse_xbrl,
    _xbrl_fact_accuracy_tolerance,
)

ANNUAL_BASIS = "ANNUAL_ALIGNED_STATEMENTS"
ALLOWED_SOURCE = "Yahoo Finance via yfinance"
REPORTING_BASIS_TAG = "NatureOfReportStandaloneConsolidated"
BORROWINGS_CURRENT_TAG = "BorrowingsCurrent"
BORROWINGS_NONCURRENT_TAG = "BorrowingsNoncurrent"
# Use total equity for both bases. In consolidated statements, EquityAttributableToOwnersOfParent
# can differ from total Equity because it excludes non-controlling interests.
EQUITY_TAG_BY_BASIS = {
    "STANDALONE": "Equity",
    "CONSOLIDATED": "Equity",
}
AUDIT_COLUMNS = [
    "TckrSymb", "ProviderDebtToEquity", "OfficialDebtToEquity",
    "DebtToEquityAuditStatus", "DebtToEquityAuditReason",
    "FinancialPeriodEnd", "OfficialFilingURL", "ReportingBasis", "XbrlContextRef",
    "EntityIdentifier", "EntityIdentifierScheme", "DimensionsJSON",
    "BorrowingsCurrentINR", "BorrowingsNoncurrentINR", "EquityINR",
    "BorrowingsCurrentFactTag", "BorrowingsNoncurrentFactTag",
    "EquityFactTag", "UnitMeasure", "TaxonomyNamespace",
    "EvidenceFilePath", "EvidenceSHA256", "XbrlAccuracyIntervalLower",
    "XbrlAccuracyIntervalUpper",
]


def _basis_value(value: str) -> str:
    text = str(value or "").strip().upper()
    if "STANDALONE" in text and "CONSOLIDATED" not in text:
        return "STANDALONE"
    if "CONSOLIDATED" in text and "STANDALONE" not in text:
        return "CONSOLIDATED"
    return ""


def _is_financial_sector(metric: pd.Series) -> bool:
    sector = _clean(metric.get("ProviderSector")).upper()
    if not sector:
        sector = _clean(metric.get("Sector")).upper()
    return any(token in sector for token in (
        "BANK", "FINANCIAL", "INSURANCE", "NBFC", "NON-BANK",
    ))


def _official_filing_row(metric: pd.Series, filings: pd.DataFrame) -> pd.Series | None:
    required = {"TckrSymb", "FinancialPeriodEnd", "OfficialFilingURL"}
    if not required.issubset(filings.columns):
        return None
    symbol = _clean(metric.get("TckrSymb")).upper()
    period = _clean(metric.get("FinancialPeriodEnd"))[:10]
    url = _clean(metric.get("OfficialFilingURL"))
    rows = filings[
        filings["TckrSymb"].astype(str).str.upper().eq(symbol)
        & filings["FinancialPeriodEnd"].astype(str).str[:10].eq(period)
        & filings["OfficialFilingURL"].astype(str).eq(url)
    ]
    return rows.iloc[0] if len(rows) == 1 else None


def _fact_in_context(
    facts: list[ET.Element], context_ref: str, tag: str,
) -> tuple[ET.Element | None, str]:
    matches = [
        fact for fact in facts
        if _local(fact.tag) == tag and fact.attrib.get("contextRef") == context_ref
    ]
    if len(matches) != 1:
        return None, f"Expected exactly one {tag} fact in context {context_ref}; found {len(matches)}"
    return matches[0], ""


def _resolve_reporting_basis(
    contexts: dict[str, dict], facts: list[ET.Element],
    instant_context: dict, period_start: str, period_end: str,
) -> tuple[str, str]:
    """Resolve basis from a matching annual duration context, not the instant ref."""
    candidates: list[str] = []
    for context_ref, context in contexts.items():
        if (
            context.get("PeriodStart") != period_start
            or context.get("PeriodEnd") != period_end
            or context.get("DimensionsJSON") != "[]"
            or context.get("EntityIdentifier") != instant_context.get("EntityIdentifier")
            or context.get("EntityIdentifierScheme") != instant_context.get("EntityIdentifierScheme")
        ):
            continue
        fact, _ = _fact_in_context(facts, context_ref, REPORTING_BASIS_TAG)
        if fact is not None:
            candidates.append(_basis_value("".join(fact.itertext())))
    candidates = [value for value in candidates if value]
    if len(candidates) != 1:
        return "", (
            "Could not resolve one standalone/consolidated basis from the matching "
            f"annual duration context; resolved values={candidates}"
        )
    return candidates[0], ""


def _ratio_accuracy_interval(
    debt: float, equity: float,
    debt_tolerance: float, equity_tolerance: float,
) -> tuple[float | None, float | None]:
    if equity <= 0 or equity - equity_tolerance <= 0:
        return None, None
    lower_debt = max(0.0, debt - debt_tolerance)
    upper_debt = debt + debt_tolerance
    lower = lower_debt / (equity + equity_tolerance)
    upper = upper_debt / (equity - equity_tolerance)
    if not all(math.isfinite(value) for value in (lower, upper)):
        return None, None
    return lower, upper


def _row(symbol: str, metric: pd.Series, status: str, reason: str, **extra) -> dict:
    row = {column: "" for column in AUDIT_COLUMNS}
    # An unavailable official ratio is missing data, never an empty-string value.
    row["OfficialDebtToEquity"] = pd.NA
    row.update({
        "TckrSymb": symbol,
        "ProviderDebtToEquity": _number(metric.get("DebtToEquity")),
        "DebtToEquityAuditStatus": status,
        "DebtToEquityAuditReason": reason,
        "FinancialPeriodEnd": _clean(metric.get("FinancialPeriodEnd"))[:10],
        "OfficialFilingURL": _clean(metric.get("OfficialFilingURL")),
    })
    row.update(extra)
    return row


def audit_ecms_debt_to_equity(
    metrics: pd.DataFrame,
    filings: pd.DataFrame,
    repo_root: str | Path,
    symbols: set[str] | list[str] | None = None,
    fetch_xml: Callable[[str, Path], object] | None = None,
) -> pd.DataFrame:
    """Recompute industrial Debt/Equity from same-context official NSE XBRL facts.

    Formula: (BorrowingsCurrent + BorrowingsNoncurrent) / Equity.
    All three facts must be unique, unsegmented, INR facts in one instant
    context. Reporting basis is independently resolved from a matching annual
    duration context and must agree with the exact official filing register.
    Financial-sector issuers are explicitly out of scope.
    """
    root = Path(repo_root).resolve()
    requested = None if symbols is None else {str(s).strip().upper() for s in symbols}
    if fetch_xml is None:
        from nse_xbrl_fetch import fetch_official_xbrl_xml
        fetch_xml = fetch_official_xbrl_xml

    rows: list[dict] = []
    if "TckrSymb" not in metrics.columns:
        return pd.DataFrame([_row("", pd.Series(dtype=object), "INPUT_SCHEMA_INVALID",
                                  "Metrics input has no TckrSymb column")], columns=AUDIT_COLUMNS)

    for _, metric in metrics.iterrows():
        symbol = _clean(metric.get("TckrSymb")).upper()
        if not symbol or (requested is not None and symbol not in requested):
            continue
        if _is_financial_sector(metric):
            rows.append(_row(symbol, metric, "NOT_APPLICABLE_FINANCIAL_SECTOR",
                             "Industrial Debt/Equity formula is not applied to banks, NBFCs, insurance or financial services"))
            continue
        provider_value = _number(metric.get("DebtToEquity"))
        if provider_value is None:
            rows.append(_row(symbol, metric, "PROVIDER_DEBT_TO_EQUITY_MISSING",
                             "Provider Debt/Equity value is missing; official reconciliation cannot be completed"))
            continue
        source = _metric_source(metric, "DebtToEquity")
        if source != ALLOWED_SOURCE:
            rows.append(_row(symbol, metric, "PROVIDER_SOURCE_NOT_APPROVED",
                             f"Expected {ALLOWED_SOURCE}; found {source or 'missing source provenance'}"))
            continue
        period = _clean(metric.get("FinancialPeriodEnd"))[:10]
        if _clean(metric.get("MetricCalculationBasis")).upper() != ANNUAL_BASIS:
            rows.append(_row(symbol, metric, "ANNUAL_BASIS_REQUIRED",
                             "Debt/Equity comparison requires annual aligned statements"))
            continue
        if not period.endswith("-03-31"):
            rows.append(_row(symbol, metric, "ANNUAL_PERIOD_UNSUPPORTED",
                             "Only March fiscal-year-end balance-sheet contexts are mapped"))
            continue
        filing_status, filing_reason = _filing_metadata_status(metric, filings)
        if filing_status != "OFFICIAL_FILING_METADATA_MATCHED":
            rows.append(_row(symbol, metric, filing_status, filing_reason))
            continue
        filing = _official_filing_row(metric, filings)
        filing_basis = _filing_reporting_basis(filing) if filing is not None else ""
        if not filing_basis:
            rows.append(_row(symbol, metric, "FILING_REPORTING_BASIS_UNRESOLVED",
                             "Exact official filing row does not identify standalone or consolidated basis"))
            continue

        url = _clean(metric.get("OfficialFilingURL"))
        parsed_url = urlsplit(url)
        if parsed_url.scheme.lower() != "https" or parsed_url.hostname != "nsearchives.nseindia.in":
            rows.append(_row(symbol, metric, "FILING_URL_NOT_OFFICIAL",
                             "XBRL download URL is not on the official NSE archives host"))
            continue
        cache_dir = root / "data" / "cache" / "ecms_debt_equity_xbrl"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = cache_dir / (hashlib.sha256(url.encode("utf-8")).hexdigest()[:20] + ".xml")
        try:
            if not cache_path.is_file():
                fetch_xml(url, cache_path)
            digest = hashlib.sha256(cache_path.read_bytes()).hexdigest()
            contexts, units, facts = _parse_xbrl(cache_path)
        except Exception as exc:
            rows.append(_row(symbol, metric, "OFFICIAL_XBRL_FETCH_OR_PARSE_FAILED",
                             f"{type(exc).__name__}: {str(exc)[:300]}"))
            continue

        start = f"{int(period[:4]) - 1}-04-01"
        instant_contexts = [
            (context_ref, context) for context_ref, context in contexts.items()
            if context.get("PeriodStart") == ""
            and context.get("PeriodEnd") == period
            and context.get("DimensionsJSON") == "[]"
            and context.get("EntityIdentifier")
        ]
        candidates = []
        basis_errors = []
        for context_ref, context in instant_contexts:
            basis, basis_reason = _resolve_reporting_basis(contexts, facts, context, start, period)
            if basis_reason:
                basis_errors.append(basis_reason)
                continue
            if basis != filing_basis:
                basis_errors.append(
                    f"XBRL duration-context basis {basis} conflicts with filing register {filing_basis}"
                )
                continue
            equity_tag = EQUITY_TAG_BY_BASIS[basis]
            selected = []
            failed = False
            for tag in (BORROWINGS_CURRENT_TAG, BORROWINGS_NONCURRENT_TAG, equity_tag):
                fact, reason = _fact_in_context(facts, context_ref, tag)
                if fact is None:
                    basis_errors.append(reason)
                    failed = True
                    break
                selected.append(fact)
            if failed:
                continue
            unit_refs = [fact.attrib.get("unitRef", "") for fact in selected]
            unit_measures = [units.get(ref, "") for ref in unit_refs]
            namespaces = [_namespace(fact.tag) for fact in selected]
            if len(set(unit_refs)) != 1 or len(set(unit_measures)) != 1:
                basis_errors.append("Borrowings and equity facts do not share one identical unitRef")
                continue
            if unit_measures[0] not in {"INR", "INR:INR"} and not unit_measures[0].endswith(":INR"):
                basis_errors.append(f"Debt/Equity components require INR; found {unit_measures[0]}")
                continue
            if len(set(namespaces)) != 1:
                basis_errors.append("Borrowings and equity facts use different taxonomy namespaces")
                continue
            values = [_fact_value(fact) for fact in selected]
            if any(value is None for value in values):
                basis_errors.append("One or more XBRL components has an invalid numeric value")
                continue
            current_debt, noncurrent_debt, equity = values
            if current_debt < 0 or noncurrent_debt < 0:
                basis_errors.append("Borrowing components cannot be negative for this ratio mapping")
                continue
            if equity <= 0:
                basis_errors.append("Equity must be positive; ratio is not meaningful for zero/negative equity")
                continue
            candidates.append((context_ref, context, selected, values, unit_measures[0], namespaces[0]))

        if len(candidates) != 1:
            status = "XBRL_INSTANT_CONTEXT_AMBIGUOUS" if len(candidates) > 1 else "XBRL_COMPONENTS_UNRESOLVED"
            reason = (
                f"Expected exactly one same-context set of current borrowings, noncurrent borrowings "
                f"and {EQUITY_TAG_BY_BASIS[filing_basis]}; found {len(candidates)}"
            )
            if basis_errors:
                reason += "; " + " | ".join(dict.fromkeys(basis_errors))[:900]
            rows.append(_row(symbol, metric, status, reason,
                             ReportingBasis=filing_basis, EvidenceFilePath=str(cache_path.relative_to(root)),
                             EvidenceSHA256=digest))
            continue

        context_ref, context, selected, values, unit_measure, namespace = candidates[0]
        current_debt, noncurrent_debt, equity = values
        official_ratio = (current_debt + noncurrent_debt) / equity
        component_tolerances = [_xbrl_fact_accuracy_tolerance(fact) for fact in selected]
        if all(value is not None for value in component_tolerances):
            debt_tol = component_tolerances[0] + component_tolerances[1]
            lower, upper = _ratio_accuracy_interval(
                current_debt + noncurrent_debt, equity, debt_tol, component_tolerances[2]
            )
        else:
            lower, upper = None, None

        if provider_value == official_ratio:
            status = "OFFICIAL_XBRL_VERIFIED"
            reason = "Exact provider equality with ratio independently recomputed from hash-identified, same-context official XBRL facts"
        elif lower is not None and lower <= provider_value <= upper:
            status = "PROVIDER_VALUE_WITHIN_XBRL_ACCURACY"
            reason = (
                "Provider value falls inside the propagated XBRL component-decimals interval; "
                "exact equality is not established"
            )
        else:
            status = "PROVIDER_VALUE_MISMATCH"
            reason = "Provider ratio differs from the official XBRL component calculation and its declared accuracy interval"

        rows.append(_row(
            symbol, metric, status, reason,
            OfficialDebtToEquity=official_ratio,
            ReportingBasis=filing_basis,
            XbrlContextRef=context_ref,
            EntityIdentifier=context.get("EntityIdentifier", ""),
            EntityIdentifierScheme=context.get("EntityIdentifierScheme", ""),
            DimensionsJSON=context.get("DimensionsJSON", ""),
            BorrowingsCurrentINR=current_debt,
            BorrowingsNoncurrentINR=noncurrent_debt,
            EquityINR=equity,
            BorrowingsCurrentFactTag=BORROWINGS_CURRENT_TAG,
            BorrowingsNoncurrentFactTag=BORROWINGS_NONCURRENT_TAG,
            EquityFactTag=EQUITY_TAG_BY_BASIS[filing_basis],
            UnitMeasure=unit_measure,
            TaxonomyNamespace=namespace,
            EvidenceFilePath=str(cache_path.relative_to(root)),
            EvidenceSHA256=digest,
            XbrlAccuracyIntervalLower=lower if lower is not None else "",
            XbrlAccuracyIntervalUpper=upper if upper is not None else "",
        ))

    return pd.DataFrame(rows, columns=AUDIT_COLUMNS)
