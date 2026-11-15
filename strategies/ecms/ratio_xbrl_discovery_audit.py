"""ECMS-only discovery audit for possible ROE, ROCE and interest-coverage XBRL facts.

This is a taxonomy-discovery report, NOT a metric verifier. Candidate facts are
never promoted to OFFICIAL_XBRL_VERIFIED; company definitions, formula,
reporting basis and period alignment require a separate approved reconciliation.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import urlsplit

import pandas as pd

from fundamental_metric_verification import _fact_value, _local, _namespace, _parse_xbrl

OUTPUT_COLUMNS = [
    "TckrSymb", "FinancialPeriodEnd", "PublicationDate", "OfficialFilingURL",
    "MetricCandidate", "DiscoveryStatus", "FactTag", "TaxonomyNamespace",
    "FactValue", "UnitMeasure", "ContextRef", "PeriodStart", "PeriodEnd",
    "ContextPeriodEndMatchesCandidate", "ContextPeriodKind", "ContextDimensionStatus",
    "DimensionsJSON", "EntityIdentifier", "EvidenceFilePath", "EvidenceSHA256",
    "VerificationWarning",
]

# Deliberately narrow: this list discovers likely ratio disclosures only.
# It does not imply that the tag definition matches ECMS's metric formula.
TAG_PATTERNS = {
    "ROEPercent": (
        "returnonequity", "returnonequityratio", "returnonshareholdersequity",
    ),
    "ROCEPercent": (
        "returnoncapitalemployed", "returnoncapitalemployedratio",
        "returnoncapital",
    ),
    "InterestCoverage": (
        "interestcoverageratio", "interestservicecoverageratio",
        "interestcoverage",
    ),
}


def _norm(value: str) -> str:
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def _candidate_metric(tag: str) -> str:
    normalized = _norm(tag)
    matches = [
        metric for metric, patterns in TAG_PATTERNS.items()
        if any(pattern in normalized for pattern in patterns)
    ]
    return matches[0] if len(matches) == 1 else ""


def _exact_filing(symbol: str, period: str, filings: pd.DataFrame):
    required = {"TckrSymb", "FinancialPeriodEnd", "OfficialFilingURL", "PublicationDateStatus"}
    if not required.issubset(filings.columns):
        return None
    rows = filings[
        filings["TckrSymb"].astype(str).str.upper().eq(symbol)
        & filings["FinancialPeriodEnd"].astype(str).str[:10].eq(period)
        & filings["PublicationDateStatus"].astype(str).eq("VERIFIED")
    ]
    return rows.iloc[0] if len(rows) == 1 else None


def discover_ecms_ratio_xbrl_facts(
    candidates: pd.DataFrame,
    filings: pd.DataFrame,
    repo_root: str | Path,
    *,
    symbols: set[str] | list[str] | None = None,
    fetch_xml=None,
) -> pd.DataFrame:
    """List likely ratio facts from exact NSE filing rows; never verifies ratios."""
    if fetch_xml is None:
        from nse_xbrl_fetch import fetch_official_xbrl_xml
        fetch_xml = fetch_official_xbrl_xml

    requested = None if symbols is None else {str(s).strip().upper() for s in symbols}
    root = Path(repo_root).resolve()
    rows: list[dict] = []

    if not {"TckrSymb", "FinancialPeriodEnd"}.issubset(candidates.columns):
        return pd.DataFrame([{
            **{column: "" for column in OUTPUT_COLUMNS},
            "DiscoveryStatus": "INPUT_SCHEMA_INVALID",
            "VerificationWarning": "Candidates require TckrSymb and FinancialPeriodEnd",
        }], columns=OUTPUT_COLUMNS)

    for _, candidate in candidates.iterrows():
        symbol = str(candidate.get("TckrSymb", "")).strip().upper()
        period = str(candidate.get("FinancialPeriodEnd", "")).strip()[:10]
        if not symbol or not period or (requested is not None and symbol not in requested):
            continue

        filing = _exact_filing(symbol, period, filings)
        if filing is None:
            rows.append({
                **{column: "" for column in OUTPUT_COLUMNS},
                "TckrSymb": symbol, "FinancialPeriodEnd": period,
                "DiscoveryStatus": "EXACT_OFFICIAL_FILING_NOT_UNIQUE",
                "VerificationWarning": "No unique exact-symbol, exact-period VERIFIED NSE filing row",
            })
            continue

        url = str(filing.get("OfficialFilingURL", "") or "").strip()
        parsed = urlsplit(url)
        if parsed.scheme.lower() != "https" or (parsed.hostname or "").lower() not in {
            "nsearchives.nseindia.com", "nsearchives.nseindia.in",
        }:
            rows.append({
                **{column: "" for column in OUTPUT_COLUMNS},
                "TckrSymb": symbol, "FinancialPeriodEnd": period,
                "PublicationDate": str(filing.get("PublicationDate", "")),
                "OfficialFilingURL": url,
                "DiscoveryStatus": "FILING_URL_NOT_OFFICIAL_OR_MISSING",
                "VerificationWarning": "Only official NSE archive XML URLs are eligible for discovery",
            })
            continue

        cache_dir = root / "data" / "cache" / "ecms_ratio_xbrl_discovery"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = cache_dir / (hashlib.sha256(url.encode("utf-8")).hexdigest()[:20] + ".xml")
        try:
            if not cache_path.is_file():
                fetch_xml(url, cache_path)
            digest = hashlib.sha256(cache_path.read_bytes()).hexdigest()
            contexts, units, facts = _parse_xbrl(cache_path)
        except Exception as exc:
            rows.append({
                **{column: "" for column in OUTPUT_COLUMNS},
                "TckrSymb": symbol, "FinancialPeriodEnd": period,
                "PublicationDate": str(filing.get("PublicationDate", "")),
                "OfficialFilingURL": url,
                "DiscoveryStatus": "OFFICIAL_XBRL_FETCH_OR_PARSE_FAILED",
                "VerificationWarning": f"{type(exc).__name__}: {str(exc)[:250]}",
            })
            continue

        found = 0
        for fact in facts:
            tag = _local(fact.tag)
            metric_name = _candidate_metric(tag)
            if not metric_name:
                continue
            context_ref = str(fact.attrib.get("contextRef", ""))
            context = contexts.get(context_ref)
            if context is None:
                continue
            value = _fact_value(fact)
            if value is None:
                continue
            found += 1
            rows.append({
                "TckrSymb": symbol,
                "FinancialPeriodEnd": period,
                "PublicationDate": str(filing.get("PublicationDate", "")),
                "OfficialFilingURL": url,
                "MetricCandidate": metric_name,
                "DiscoveryStatus": "CANDIDATE_FACT_DISCOVERY_ONLY",
                "FactTag": tag,
                "TaxonomyNamespace": _namespace(fact.tag),
                "FactValue": value,
                "UnitMeasure": units.get(str(fact.attrib.get("unitRef", "")), ""),
                "ContextRef": context_ref,
                "PeriodStart": context.get("PeriodStart", ""),
                "PeriodEnd": context.get("PeriodEnd", ""),
                "ContextPeriodEndMatchesCandidate": str(context.get("PeriodEnd", "")).strip()[:10] == period,
                "ContextPeriodKind": "DURATION" if context.get("PeriodStart") else "INSTANT_OR_UNKNOWN",
                "ContextDimensionStatus": "DIMENSIONED" if context.get("DimensionsJSON", "[]") not in {"", "[]"} else "UNSEGMENTED",
                "DimensionsJSON": context.get("DimensionsJSON", ""),
                "EntityIdentifier": context.get("EntityIdentifier", ""),
                "EvidenceFilePath": str(cache_path),
                "EvidenceSHA256": digest,
                "VerificationWarning": (
                    "Discovery only: context end-date must match candidate period; also verify taxonomy "
                    "definition, formula, duration, basis, dimensions and provider reconciliation"
                ),
            })
        if found == 0:
            rows.append({
                **{column: "" for column in OUTPUT_COLUMNS},
                "TckrSymb": symbol, "FinancialPeriodEnd": period,
                "PublicationDate": str(filing.get("PublicationDate", "")),
                "OfficialFilingURL": url,
                "DiscoveryStatus": "NO_RATIO_CANDIDATE_FACT_FOUND",
                "EvidenceFilePath": str(cache_path),
                "EvidenceSHA256": digest,
                "VerificationWarning": "No matching numeric ROE/ROCE/interest-coverage fact tag found",
            })

    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
