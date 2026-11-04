"""Strong-fundamental shortlist for NSE V8 (separate, metadata-only stage).

Uses ABSOLUTE thresholds (not daily percentiles), so a stock's status does not
change just because other candidates were weaker or stronger that day.

Statuses:
  PASS            every required metric is present, verified point-in-time and meets its threshold
  FAIL            data is verified and complete but at least one threshold is not met
  WAIT_FOR_DATA   metrics missing, publication date / metric-period alignment / calculation
                  basis unverified, or sector needs different rules (banks, NBFCs, insurers)

Missing or unverified data is never PASS and never guessed. This function
preserves every input row while adding a status and writing reports. The
production pipeline advances only explicit PASS rows through its fundamental
hard gate; WAIT and FAIL rows remain visible in the collection reports.

Thresholds are starting points. Override any of them in
data/inputs/fundamental_thresholds.json (keys with null/absent keep the default).
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

OUTPUT_DIR = Path("outputs")
THRESHOLDS_PATH = Path("data") / "inputs" / "fundamental_thresholds.json"

DEFAULT_THRESHOLDS = {
    "min_revenue_growth_pct": 0.0,
    "min_profit_growth_pct": 0.0,
    "min_roe_pct": 10.0,
    "min_roce_pct": 12.0,
    "max_debt_to_equity": 1.0,
    "min_interest_coverage": 3.0,
    "require_positive_operating_cash_flow": True,
    "require_positive_free_cash_flow": False,  # growth companies often have negative FCF
    # Annual statements are used, so ~18 months is the natural staleness limit.
    "max_data_age_days": 548,
}

# Debt/equity, ROCE and interest coverage are not meaningful for lenders/insurers.
SPECIAL_RULE_SECTORS = {"financial services", "financial", "banks", "insurance"}

ALLOWED_METRIC_CALCULATION_BASES = {
    "QUARTERLY_TTM_ALIGNED_STATEMENTS",
    "ANNUAL_ALIGNED_STATEMENTS",
}

REQUIRED_METRICS = {
    "RevenueGrowthPct": "min_revenue_growth_pct",
    "ProfitGrowthPct": "min_profit_growth_pct",
    "ROEPercent": "min_roe_pct",
    "ROCEPercent": "min_roce_pct",
    "DebtToEquity": "max_debt_to_equity",
    "InterestCoverage": "min_interest_coverage",
    "OperatingCashFlowINR": "require_positive_operating_cash_flow",
}


def load_thresholds(path: str | Path = THRESHOLDS_PATH) -> dict:
    thresholds = dict(DEFAULT_THRESHOLDS)
    path = Path(path)
    if path.exists() and path.stat().st_size:
        try:
            user = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            user = {}
        for key in DEFAULT_THRESHOLDS:
            if user.get(key) is not None:
                thresholds[key] = user[key]
    return thresholds


def _num(value):
    return pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]


def _evaluate_row(row: pd.Series, asof, t: dict,
                  metric_verification_by_symbol: dict[str, dict[str, str]] | None = None) -> tuple[str, str]:
    # Duplicate metric records make the selected row ambiguous. Do not let a
    # valid-looking last row silently PASS while the collection audit flags a
    # duplicate for the same symbol.
    collection_reason = str(row.get("FundamentalReason", "") or "")
    if "DUPLICATE_FUNDAMENTAL_RECORDS" in collection_reason:
        return "WAIT_FOR_DATA", "DUPLICATE_FUNDAMENTAL_RECORDS; resolve cache/input rows before assessment"

    sector = str(row.get("ProviderSector", "") or "").strip().lower()
    if sector in SPECIAL_RULE_SECTORS:
        return "WAIT_FOR_DATA", "SECTOR_NEEDS_SPECIAL_RULES(NIM/GNPA/CAR); manual review"

    waits = []
    if str(row.get("PublicationDateStatus", "")).strip().upper() != "VERIFIED":
        waits.append("PUBLICATION_DATE_UNVERIFIED")
    if str(row.get("MetricPeriodAlignmentStatus", "")).strip().upper() != "VERIFIED":
        waits.append("METRIC_PERIOD_ALIGNMENT_UNVERIFIED")
    calculation_basis = str(row.get("MetricCalculationBasis", "")).strip().upper()
    if calculation_basis not in ALLOWED_METRIC_CALCULATION_BASES:
        waits.append("METRIC_CALCULATION_BASIS_UNKNOWN_OR_UNSUPPORTED")
    period_end = pd.to_datetime(row.get("FinancialPeriodEnd"), errors="coerce")
    publication = pd.to_datetime(row.get("PublicationDate"), errors="coerce")
    if pd.isna(period_end):
        waits.append("FINANCIAL_PERIOD_END_MISSING")
    if pd.isna(publication):
        waits.append("PUBLICATION_DATE_MISSING")
    if pd.notna(asof):
        if pd.notna(period_end) and period_end.normalize() > asof.normalize():
            waits.append("PERIOD_END_AFTER_EOD")
        if pd.notna(publication) and publication.normalize() > asof.normalize():
            waits.append("PUBLICATION_AFTER_EOD")
        max_age = t.get("max_data_age_days")
        if max_age is not None and pd.notna(period_end) and (asof.normalize() - period_end.normalize()).days > float(max_age):
            waits.append(f"DATA_OLDER_THAN_{int(max_age)}_DAYS")
    values = {m: _num(row.get(m)) for m in REQUIRED_METRICS}
    missing = [m for m, v in values.items() if pd.isna(v)]
    if missing:
        waits.append("MISSING_METRICS:" + ",".join(missing))
    if waits:
        return "WAIT_FOR_DATA", ";".join(waits)

    # When the production pipeline supplies the independent XBRL audit, do not
    # treat filing metadata or a provider calculation basis as proof that the
    # numeric values match official filings. Every metric used by the hard
    # fundamental gate must have an exact official metric-level verification.
    if metric_verification_by_symbol is not None:
        symbol = str(row.get("TckrSymb", "")).strip().upper()
        verified_metrics = metric_verification_by_symbol.get(symbol, {})
        unverified = []
        for metric in REQUIRED_METRICS:
            status = verified_metrics.get(metric, "NO_AUDIT_ROW")
            if status != "OFFICIAL_XBRL_VERIFIED":
                unverified.append(f"{metric}={status}")
        if unverified:
            return "WAIT_FOR_DATA", "OFFICIAL_METRICS_NOT_VERIFIED:" + ",".join(unverified)

    fails = []
    checks = [
        ("RevenueGrowthPct", ">=", t["min_revenue_growth_pct"]),
        ("ProfitGrowthPct", ">=", t["min_profit_growth_pct"]),
        ("ROEPercent", ">=", t["min_roe_pct"]),
        ("ROCEPercent", ">=", t["min_roce_pct"]),
        ("DebtToEquity", "<=", t["max_debt_to_equity"]),
        ("InterestCoverage", ">=", t["min_interest_coverage"]),
    ]
    for metric, op, limit in checks:
        if limit is None:
            continue
        v = values[metric]
        if (op == ">=" and v < float(limit)) or (op == "<=" and v > float(limit)):
            fails.append(f"{metric}={v:.2f}{'<' if op == '>=' else '>'}{limit}")
    if t.get("require_positive_operating_cash_flow") and values["OperatingCashFlowINR"] <= 0:
        fails.append("OperatingCashFlow<=0")
    if t.get("require_positive_free_cash_flow"):
        fcf = _num(row.get("FreeCashFlowINR"))
        if pd.isna(fcf):
            return "WAIT_FOR_DATA", "MISSING_METRICS:FreeCashFlowINR"
        if fcf <= 0:
            fails.append("FreeCashFlow<=0")
    if fails:
        return "FAIL", ";".join(fails)
    return "PASS", "ALL_THRESHOLDS_MET"


def build_fundamental_shortlist(audit: pd.DataFrame, asof_date, thresholds: dict | None = None,
                                write: bool = True,
                                metric_verification: pd.DataFrame | None = None) -> pd.DataFrame:
    """Return `audit` with FundamentalShortlistStatus/Reason; never drops rows.

    Production callers pass the independent metric-level XBRL audit. Omitting
    it remains supported for isolated legacy callers, but is not the production
    selection path.
    """
    t = thresholds if thresholds is not None else load_thresholds()
    asof = pd.to_datetime(asof_date, errors="coerce")
    result = audit.copy()
    if result.empty:
        result["FundamentalShortlistStatus"] = pd.Series(dtype=str)
        result["FundamentalShortlistReason"] = pd.Series(dtype=str)
    else:
        verification_by_symbol = None
        if metric_verification is not None:
            verification_by_symbol = {}
            required_columns = {"TckrSymb", "MetricName", "MetricValueVerificationStatus"}
            if required_columns.issubset(metric_verification.columns):
                for _, metric_row in metric_verification.iterrows():
                    symbol = str(metric_row.get("TckrSymb", "")).strip().upper()
                    metric = str(metric_row.get("MetricName", "")).strip()
                    status = str(metric_row.get("MetricValueVerificationStatus", "")).strip().upper()
                    if symbol and metric:
                        verification_by_symbol.setdefault(symbol, {})[metric] = status or "NO_VERIFICATION_STATUS"
        evaluated = result.apply(lambda r: _evaluate_row(r, asof, t, verification_by_symbol), axis=1)
        result["FundamentalShortlistStatus"] = [e[0] for e in evaluated]
        result["FundamentalShortlistReason"] = [e[1] for e in evaluated]
    # Keep the two public assessment fields in sync at the source of truth,
    # including callers outside volume_gainer.py and error/report workflows.
    result["FundamentalAssessmentStatus"] = result["FundamentalShortlistStatus"].astype(str)
    result["FundamentalAssessmentReason"] = result["FundamentalShortlistReason"].astype(str)
    if write:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        result.to_csv(OUTPUT_DIR / "v8_fundamental_shortlist_all.csv", index=False)
        result[result["FundamentalShortlistStatus"] == "PASS"].to_csv(
            OUTPUT_DIR / "v8_fundamental_shortlist_pass.csv", index=False)
    return result

