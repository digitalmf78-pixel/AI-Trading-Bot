"""Audit-only Q4 CFO derivation from official annual and 9M NSE XBRL filings.

This module downloads the annual and nine-month cumulative filings for the same
symbol/reporting basis, validates period/entity/unit/taxonomy alignment, and
calculates Annual CFO - 9M YTD CFO as a DERIVED CANDIDATE ONLY. It never updates
the Fundamental cache or promotes a value to VERIFIED.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd

from nse_xbrl_fetch import fetch_official_xbrl_xml
from nse_xbrl_statement_reconciliation import inspect_statement

CFO_TAG = "CashFlowsFromUsedInOperatingActivities"
ALLOWED_HOST = "nsearchives.nseindia.com"
DEFAULT_PRIORITY = ("SETCO", "NIRAJ", "LAL", "DONEAR", "DNAMEDIA")


def _basis_from_description(value: object) -> str:
    text = str(value or "").upper()
    has_standalone = bool(re.search(r"\bSTANDALONE\b", text))
    has_consolidated = bool(re.search(r"\bCONSOLIDATED\b", text))
    if has_standalone == has_consolidated:
        return "UNKNOWN"
    return "STANDALONE" if has_standalone else "CONSOLIDATED"


def _is_official_verified(row: pd.Series, cutoff: pd.Timestamp) -> bool:
    if str(row.get("PublicationDateStatus", "")).strip().upper() != "VERIFIED":
        return False
    pub = pd.to_datetime(row.get("PublicationDate"), errors="coerce")
    url = str(row.get("OfficialFilingURL", "")).strip()
    return bool(
        pd.notna(pub) and pub.normalize() <= cutoff
        and url.startswith("https://")
        and (url.split("/", 3)[2].lower() == ALLOWED_HOST)
    )


def _latest_filing(rows: pd.DataFrame) -> pd.Series | None:
    if rows.empty:
        return None
    ordered = rows.copy()
    ordered["_pub"] = pd.to_datetime(ordered["PublicationDate"], errors="coerce")
    ordered["_revision"] = ordered.get("FilingDescription", pd.Series("", index=ordered.index)).astype(str).str.contains(
        r"\bREVISION\b", case=False, regex=True
    ).astype(int)
    ordered = ordered.sort_values(["_pub", "_revision", "OfficialFilingURL"], ascending=[False, False, True])
    return ordered.iloc[0]


def select_annual_ytd_pairs(metrics: pd.DataFrame, filings: pd.DataFrame, cutoff_date: str,
                            limit: int = 5, priority_symbols=DEFAULT_PRIORITY) -> list[dict]:
    """Select exact annual filing URL + same-basis 9M filing pairs.

    The annual URL must be the one already attached to the fundamental record.
    This prevents choosing an arbitrary standalone/consolidated alternative.
    """
    cutoff = pd.to_datetime(cutoff_date, errors="coerce")
    if pd.isna(cutoff):
        raise ValueError(f"Invalid cutoff date: {cutoff_date}")
    cutoff = cutoff.normalize()
    required_metrics = {"TckrSymb", "FinancialPeriodEnd", "OfficialFilingURL", "MetricCalculationBasis"}
    required_filings = {"TckrSymb", "FinancialPeriodEnd", "PublicationDate", "PublicationDateStatus", "FilingDescription", "OfficialFilingURL"}
    if not required_metrics.issubset(metrics.columns):
        raise ValueError(f"Fundamental metrics missing columns: {sorted(required_metrics - set(metrics.columns))}")
    if not required_filings.issubset(filings.columns):
        raise ValueError(f"Official filings missing columns: {sorted(required_filings - set(filings.columns))}")

    legacy = metrics.copy()
    legacy["TckrSymb"] = legacy["TckrSymb"].astype(str).str.strip().str.upper()
    legacy = legacy[legacy["MetricCalculationBasis"].astype(str).str.upper().eq("LEGACY_CACHE_BASIS_UNKNOWN")]
    legacy["_annual_end"] = pd.to_datetime(legacy["FinancialPeriodEnd"], errors="coerce").dt.normalize()
    legacy = legacy[
        legacy["_annual_end"].notna()
        & legacy["_annual_end"].dt.is_month_end
        & legacy["_annual_end"].dt.month.eq(3)
        & legacy["_annual_end"].dt.day.eq(31)
    ]
    if "OperatingCashFlowINR" in legacy.columns:
        legacy = legacy[pd.to_numeric(legacy["OperatingCashFlowINR"], errors="coerce").notna()]

    filing_rows = filings.copy()
    filing_rows["TckrSymb"] = filing_rows["TckrSymb"].astype(str).str.strip().str.upper()
    filing_rows["FinancialPeriodEnd"] = pd.to_datetime(filing_rows["FinancialPeriodEnd"], errors="coerce").dt.strftime("%Y-%m-%d")
    filing_rows["_publication_parsed"] = pd.to_datetime(filing_rows["PublicationDate"], errors="coerce").dt.normalize()
    filing_rows["_url_host"] = filing_rows["OfficialFilingURL"].astype(str).str.extract(r"^https://([^/]+)", expand=False).str.lower()
    filing_rows["_basis"] = filing_rows["FilingDescription"].map(_basis_from_description)
    filing_rows = filing_rows[
        filing_rows["PublicationDateStatus"].astype(str).str.upper().eq("VERIFIED")
        & filing_rows["_publication_parsed"].notna()
        & filing_rows["_publication_parsed"].le(cutoff)
        & filing_rows["_url_host"].eq(ALLOWED_HOST)
    ]

    priority = {str(s).upper(): i for i, s in enumerate(priority_symbols)}
    legacy["_priority"] = legacy["TckrSymb"].map(lambda s: priority.get(s, 999))
    legacy = legacy.sort_values(["_priority", "TckrSymb"])
    pairs = []
    for _, metric in legacy.iterrows():
        symbol = metric["TckrSymb"]
        annual_url = str(metric.get("OfficialFilingURL", "")).strip()
        annual_period_end = metric["_annual_end"].date().isoformat()
        nine_month_period_end = (metric["_annual_end"] - pd.DateOffset(months=3)).date().isoformat()
        fiscal_start = (metric["_annual_end"] - pd.DateOffset(years=1) + pd.Timedelta(days=1)).date().isoformat()
        annual_candidates = filing_rows[
            filing_rows["TckrSymb"].eq(symbol)
            & filing_rows["FinancialPeriodEnd"].eq(annual_period_end)
            & filing_rows["OfficialFilingURL"].astype(str).eq(annual_url)
        ]
        annual = _latest_filing(annual_candidates)
        if annual is None:
            continue
        basis = str(annual["_basis"])
        if basis not in {"STANDALONE", "CONSOLIDATED"}:
            continue
        ytd_candidates = filing_rows[
            filing_rows["TckrSymb"].eq(symbol)
            & filing_rows["FinancialPeriodEnd"].eq(nine_month_period_end)
            & filing_rows["_basis"].eq(basis)
        ]
        ytd = _latest_filing(ytd_candidates)
        if ytd is None:
            continue
        pairs.append({
            "Symbol": symbol,
            "AnnualPeriodEnd": annual_period_end,
            "NineMonthPeriodEnd": nine_month_period_end,
            "FiscalStartDate": fiscal_start,
            "ProviderCFOINR": metric.get("OperatingCashFlowINR", pd.NA),
            "ProviderSource": metric.get("Source", ""),
            "ProviderCalculationBasis": metric.get("MetricCalculationBasis", ""),
            "ProviderCashFlowPeriodBasis": metric.get("CashFlowPeriodBasis", ""),
            "AnnualFilingURL": str(annual["OfficialFilingURL"]),
            "AnnualPublicationDate": str(annual["PublicationDate"]),
            "AnnualFilingDescription": str(annual["FilingDescription"]),
            "AnnualReportingBasisExpected": basis,
            "NineMonthFilingURL": str(ytd["OfficialFilingURL"]),
            "NineMonthPublicationDate": str(ytd["PublicationDate"]),
            "NineMonthFilingDescription": str(ytd["FilingDescription"]),
            "NineMonthReportingBasisExpected": str(ytd["_basis"]),
        })
        if len(pairs) >= max(1, int(limit)):
            break
    return pairs


def _extract_unique_cfo(statement: dict, *, expected_symbol: str, expected_basis: str,
                        expected_start: str, expected_end: str) -> tuple[dict | None, str]:
    if statement.get("IdentityStatus") != "MATCH":
        return None, "XML_SYMBOL_IDENTITY_NOT_CONFIRMED"
    facts = [f for f in statement.get("Facts", []) if f.get("Tag") == CFO_TAG]
    matched = []
    for fact in facts:
        if (fact.get("StartDate") == expected_start and fact.get("EndDate") == expected_end
                and fact.get("ReportingBasis") == expected_basis
                and fact.get("PeriodClass") in {"ANNUAL_12M_CANDIDATE", "YTD_9M_CANDIDATE"}):
            matched.append(fact)
    if len(matched) != 1:
        return None, f"EXPECTED_EXACTLY_ONE_CFO_FACT_FOUND_{len(matched)}"
    fact = matched[0]
    if fact.get("DimensionsJSON") != "[]":
        return None, "DIMENSIONED_CFO_FACT_REQUIRES_REVIEW"
    if fact.get("UnitMeasure") != "iso4217:INR":
        return None, f"UNSUPPORTED_CFO_UNIT:{fact.get('UnitMeasure')}"
    try:
        Decimal(str(fact.get("Value", "")))
    except (InvalidOperation, ValueError):
        return None, "CFO_VALUE_NOT_NUMERIC"
    return fact, "PASS"


def _decimals_tolerance(*facts: dict) -> Decimal:
    tolerance = Decimal(0)
    for fact in facts:
        raw = str(fact.get("Decimals", "")).strip()
        if not raw or raw.upper() == "INF":
            continue
        try:
            tolerance += (Decimal(10) ** (-int(raw))) / Decimal(2)
        except (ValueError, InvalidOperation, OverflowError):
            continue
    return tolerance


def reconcile_pair(pair: dict, annual_statement: dict, ytd_statement: dict) -> dict:
    base = dict(pair)
    annual_basis = pair["AnnualReportingBasisExpected"]
    ytd_basis = pair["NineMonthReportingBasisExpected"]
    annual_fact, annual_status = _extract_unique_cfo(
        annual_statement, expected_symbol=pair["Symbol"], expected_basis=annual_basis,
        expected_start=pair["FiscalStartDate"], expected_end=pair["AnnualPeriodEnd"],
    )
    ytd_fact, ytd_status = _extract_unique_cfo(
        ytd_statement, expected_symbol=pair["Symbol"], expected_basis=ytd_basis,
        expected_start=pair["FiscalStartDate"], expected_end=pair["NineMonthPeriodEnd"],
    )
    if annual_fact is None or ytd_fact is None:
        base.update({
            "Status": "WAIT_FOR_DATA",
            "Reason": f"ANNUAL:{annual_status};NINE_MONTH:{ytd_status}",
            "AnnualCFOINR": pd.NA, "NineMonthYTD_CFOINR": pd.NA,
            "DerivedQ4CFOINR": pd.NA, "RoundingToleranceINR": pd.NA,
            "VerificationStatus": "NOT_VERIFIED",
        })
        return base

    checks = [
        (annual_statement.get("IdentityStatus") == "MATCH", "ANNUAL_IDENTITY_MISMATCH"),
        (ytd_statement.get("IdentityStatus") == "MATCH", "NINE_MONTH_IDENTITY_MISMATCH"),
        (annual_basis == ytd_basis, "REPORTING_BASIS_MISMATCH"),
        (annual_fact.get("EntityIdentifier") == ytd_fact.get("EntityIdentifier"), "ENTITY_IDENTIFIER_MISMATCH"),
        (annual_fact.get("EntityIdentifierScheme") == ytd_fact.get("EntityIdentifierScheme"), "ENTITY_SCHEME_MISMATCH"),
        (annual_fact.get("UnitMeasure") == ytd_fact.get("UnitMeasure"), "UNIT_MISMATCH"),
        (annual_fact.get("Namespace") == ytd_fact.get("Namespace"), "TAXONOMY_NAMESPACE_MISMATCH"),
    ]
    failed = [reason for ok, reason in checks if not ok]
    if failed:
        base.update({
            "Status": "WAIT_FOR_DATA", "Reason": ";".join(failed),
            "AnnualCFOINR": str(annual_fact["Value"]),
            "NineMonthYTD_CFOINR": str(ytd_fact["Value"]),
            "DerivedQ4CFOINR": pd.NA, "RoundingToleranceINR": pd.NA,
            "VerificationStatus": "NOT_VERIFIED",
        })
        return base

    annual_value = Decimal(str(annual_fact["Value"]))
    ytd_value = Decimal(str(ytd_fact["Value"]))
    derived = annual_value - ytd_value
    tolerance = _decimals_tolerance(annual_fact, ytd_fact)
    provider_basis = str(pair.get("ProviderCalculationBasis", "")).strip().upper()
    provider_cash_basis = str(pair.get("ProviderCashFlowPeriodBasis", "")).strip().upper()
    provider_comparison = (
        "NOT_COMPARABLE_PROVIDER_BASIS_UNKNOWN"
        if provider_basis in {"", "LEGACY_CACHE_BASIS_UNKNOWN", "UNALIGNED_PROVIDER_SNAPSHOT"}
        or provider_cash_basis in {"", "UNKNOWN", "NAN"}
        else "REFERENCE_ONLY_PROVIDER_REPORTING_BASIS_NOT_PROVEN"
    )
    base.update({
        "Status": "DERIVED_Q4_CFO_CANDIDATE_ONLY",
        "Reason": "Annual standalone/consolidated CFO minus same-basis 9M YTD CFO; candidate only; not promoted to cache",
        "AnnualCFOINR": str(annual_value),
        "NineMonthYTD_CFOINR": str(ytd_value),
        "DerivedQ4CFOINR": str(derived),
        "RoundingToleranceINR": str(tolerance),
        "AnnualContextRef": annual_fact.get("ContextRef", ""),
        "NineMonthContextRef": ytd_fact.get("ContextRef", ""),
        "EntityIdentifier": annual_fact.get("EntityIdentifier", ""),
        "EntityIdentifierScheme": annual_fact.get("EntityIdentifierScheme", ""),
        "UnitMeasure": annual_fact.get("UnitMeasure", ""),
        "TaxonomyNamespace": annual_fact.get("Namespace", ""),
        "AnnualDecimals": annual_fact.get("Decimals", ""),
        "NineMonthDecimals": ytd_fact.get("Decimals", ""),
        "ProviderComparisonStatus": provider_comparison,
        "VerificationStatus": "DERIVED_CANDIDATE_ONLY_NOT_VERIFIED",
    })
    return base


def infer_cutoff_date(metrics_path: str | Path, shortlist_path: str | Path = "outputs/v8_final_shortlist.csv") -> str:
    shortlist = Path(shortlist_path)
    if shortlist.exists() and shortlist.stat().st_size:
        try:
            frame = pd.read_csv(shortlist)
            for column in ("TradDt", "BizDt", "AsOfDate"):
                if column in frame:
                    values = pd.to_datetime(frame[column], errors="coerce").dropna()
                    if not values.empty:
                        return values.max().date().isoformat()
        except Exception:
            pass
    metrics = pd.read_csv(metrics_path)
    if "AsOfDate" in metrics:
        values = pd.to_datetime(metrics["AsOfDate"], errors="coerce").dropna()
        if not values.empty:
            return values.max().date().isoformat()
    raise ValueError("Unable to infer EOD cutoff from final shortlist or fundamental metrics")


def run_audit(metrics_path: str | Path, filings_path: str | Path, output_dir: str | Path,
              cutoff_date: str | None = None, limit: int = 5, pause_seconds: float = 0.2,
              fetcher=None) -> dict:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    metrics = pd.read_csv(metrics_path)
    filings = pd.read_csv(filings_path)
    cutoff_date = cutoff_date or infer_cutoff_date(metrics_path)
    pairs = select_annual_ytd_pairs(metrics, filings, cutoff_date, limit=limit)
    results = []
    cache = Path("data/cache/xbrl_period_pairs")
    cache.mkdir(parents=True, exist_ok=True)
    downloader = fetcher or fetch_official_xbrl_xml

    for pair in pairs:
        parsed_statements = []
        errors = []
        for key, url, _expected_period, _expected_basis in (
            ("annual", pair["AnnualFilingURL"], pair["AnnualPeriodEnd"], pair["AnnualReportingBasisExpected"]),
            ("nine_month", pair["NineMonthFilingURL"], pair["NineMonthPeriodEnd"], pair["NineMonthReportingBasisExpected"]),
        ):
            target = cache / f"{hashlib.sha256(url.encode('utf-8')).hexdigest()[:16]}.xml"
            try:
                if not target.exists():
                    downloader(url, target)
                    if pause_seconds > 0:
                        time.sleep(pause_seconds)
                statement = inspect_statement(
                    target, symbol=pair["Symbol"], official_filing_url=url,
                    publication_date=pair["AnnualPublicationDate"] if key == "annual" else pair["NineMonthPublicationDate"],
                )
                if statement.get("IdentityStatus") != "MATCH":
                    errors.append(f"{key.upper()}_XML_SYMBOL_IDENTITY_NOT_CONFIRMED")
                parsed_statements.append(statement)
            except Exception as exc:
                errors.append(f"{key.upper()}_FETCH_OR_PARSE_FAILED:{type(exc).__name__}:{exc}"[:400])
                parsed_statements.append(None)
        if errors or any(s is None for s in parsed_statements):
            results.append({**pair, "Status": "WAIT_FOR_DATA", "Reason": ";".join(errors) or "XML_UNAVAILABLE",
                            "VerificationStatus": "NOT_VERIFIED"})
            continue
        result = reconcile_pair(pair, parsed_statements[0], parsed_statements[1])
        results.append(result)

    report = {
        "Status": "SUCCESS" if results else "NO_ELIGIBLE_ANNUAL_YTD_PAIRS",
        "CutoffDate": cutoff_date,
        "CandidatePairs": len(pairs),
        "ProcessedPairs": len(results),
        "DerivedCandidateCount": sum(r.get("Status") == "DERIVED_Q4_CFO_CANDIDATE_ONLY" for r in results),
        "WaitForDataCount": sum(r.get("Status") == "WAIT_FOR_DATA" for r in results),
        "Results": results,
        "SafetyNote": "This diagnostic does not update Fundamental Cache, calculate TTM, or mark any value VERIFIED.",
    }
    (output / "xbrl_ytd_cashflow_reconciliation.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    pd.DataFrame(results).to_csv(output / "xbrl_ytd_cashflow_reconciliation.csv", index=False)
    summary = pd.DataFrame([{
        "Status": report["Status"], "CandidatePairs": report["CandidatePairs"],
        "ProcessedPairs": report["ProcessedPairs"], "DerivedCandidateCount": report["DerivedCandidateCount"],
        "WaitForDataCount": report["WaitForDataCount"],
        "VerificationStatus": "DERIVED_CANDIDATE_ONLY_NOT_VERIFIED",
    }])
    summary.to_csv(output / "xbrl_ytd_cashflow_reconciliation_summary.csv", index=False)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metrics", default="data/inputs/fundamental_metrics.csv")
    parser.add_argument("--filings", default="outputs/v8_official_financial_results_filings.csv")
    parser.add_argument("--output", default="outputs/xbrl_ytd_cashflow_reconciliation")
    parser.add_argument("--cutoff", default=None, help="EOD cutoff; inferred from final shortlist when omitted")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--pause-seconds", type=float, default=0.2)
    args = parser.parse_args(argv)
    report = run_audit(args.metrics, args.filings, args.output, args.cutoff,
                       limit=args.limit, pause_seconds=args.pause_seconds)
    print(json.dumps({k: report.get(k) for k in (
        "Status", "CandidatePairs", "ProcessedPairs", "DerivedCandidateCount", "WaitForDataCount"
    )}))
    return 0  # audit-only; inspect report statuses separately


if __name__ == "__main__":
    raise SystemExit(main())
