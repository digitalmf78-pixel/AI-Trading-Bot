"""Strong-fundamental shortlist for NSE V8 (separate, metadata-only stage).

Uses ABSOLUTE thresholds (not daily percentiles), so a stock's status does not
change just because other candidates were weaker or stronger that day.

Statuses:
  PASS            every required metric is present, verified point-in-time and meets its threshold
  FAIL            data is verified and complete but at least one threshold is not met
  WAIT_FOR_DATA   metrics missing, publication date / metric-period alignment unverified,
                  or sector needs different rules (banks, NBFCs, insurers)

Missing or unverified data is never PASS and never guessed. This stage does not
remove rows from the main pipeline; it only adds a status and writes a report.

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


def _evaluate_row(row: pd.Series, asof, t: dict) -> tuple[str, str]:
    sector = str(row.get("ProviderSector", "") or "").strip().lower()
    if sector in SPECIAL_RULE_SECTORS:
        return "WAIT_FOR_DATA", "SECTOR_NEEDS_SPECIAL_RULES(NIM/GNPA/CAR); manual review"

    waits = []
    if str(row.get("PublicationDateStatus", "")).strip().upper() != "VERIFIED":
        waits.append("PUBLICATION_DATE_UNVERIFIED")
    if str(row.get("MetricPeriodAlignmentStatus", "")).strip().upper() != "VERIFIED":
        waits.append("METRIC_PERIOD_ALIGNMENT_UNVERIFIED")
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
                                write: bool = True) -> pd.DataFrame:
    """Return `audit` with FundamentalShortlistStatus/Reason; never drops rows."""
    t = thresholds if thresholds is not None else load_thresholds()
    asof = pd.to_datetime(asof_date, errors="coerce")
    result = audit.copy()
    if result.empty:
        result["FundamentalShortlistStatus"] = pd.Series(dtype=str)
        result["FundamentalShortlistReason"] = pd.Series(dtype=str)
    else:
        evaluated = result.apply(lambda r: _evaluate_row(r, asof, t), axis=1)
        result["FundamentalShortlistStatus"] = [e[0] for e in evaluated]
        result["FundamentalShortlistReason"] = [e[1] for e in evaluated]
    if write:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        result.to_csv(OUTPUT_DIR / "v8_fundamental_shortlist_all.csv", index=False)
        result[result["FundamentalShortlistStatus"] == "PASS"].to_csv(
            OUTPUT_DIR / "v8_fundamental_shortlist_pass.csv", index=False)
    return result
