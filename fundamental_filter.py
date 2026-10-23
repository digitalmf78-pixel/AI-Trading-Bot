"""Fundamental data collection and provisional scoring for NSE V8.

This stage is intentionally NOT a hard eligibility filter. Every stock that
passes Delivery Category A or B remains in the fundamental collection reports,
even when its financial data is missing or incomplete. Strong-fundamental
shortlisting is a later, separate decision.
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

INPUT_DIR = Path("data") / "inputs"
OUTPUT_DIR = Path("outputs")
METRICS_PATH = INPUT_DIR / "fundamental_metrics.csv"
THRESHOLDS_PATH = INPUT_DIR / "fundamental_thresholds.json"

METRIC_COLUMNS = [
    "RevenueGrowthPct", "ProfitGrowthPct", "ROEPercent", "ROCEPercent",
    "DebtToEquity", "InterestCoverage", "OperatingCashFlowINR",
    "FreeCashFlowINR", "EarningsQualityStatus", "ValuationStatus",
]
SOURCE_COLUMNS = [
    "TckrSymb", "AsOfDate", "DataRetrievedAtUTC", "Source", "SourceURL",
    "FinancialPeriodEnd", "PublicationDate", "PublicationDateStatus",
    "OfficialFilingURL", "OfficialFilingSource", "MetricPeriodAlignmentStatus",
]
INPUT_COLUMNS = SOURCE_COLUMNS + METRIC_COLUMNS
STATUS_COLUMNS = [
    "FundamentalStatus", "FundamentalReason", "FundamentalAsOfDate",
    "FundamentalSource", "FundamentalSourceURL",
    "FundamentalMetricsCompletenessPct", "FundamentalScoreCoveragePct",
    "FundamentalAssessmentStatus",
]
SCORE_METRICS = {
    "RevenueGrowthPct": True,
    "ProfitGrowthPct": True,
    "ROEPercent": True,
    "ROCEPercent": True,
    "DebtToEquity": False,
    "InterestCoverage": True,
}


def create_fundamental_templates() -> None:
    """Create blank input templates if missing; never fabricate financial data."""
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if not METRICS_PATH.exists():
        pd.DataFrame(columns=INPUT_COLUMNS).to_csv(METRICS_PATH, index=False)
    if not THRESHOLDS_PATH.exists():
        # Retained for backward compatibility. Thresholds are not used during
        # collection; they belong to the later strong-fundamental shortlist.
        template = {
            "min_revenue_growth_pct": None,
            "min_profit_growth_pct": None,
            "min_roe_pct": None,
            "min_roce_pct": None,
            "max_debt_to_equity": None,
            "min_interest_coverage": None,
            "require_positive_operating_cash_flow": None,
            "require_positive_free_cash_flow": None,
            "acceptable_earnings_quality_status": None,
            "acceptable_valuation_status": None,
            "max_data_age_days": None,
        }
        THRESHOLDS_PATH.write_text(json.dumps(template, indent=2) + "\n", encoding="utf-8")


def _nonempty(value) -> bool:
    return pd.notna(value) and str(value).strip() != ""


def _number(value):
    return pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]


def _load_inputs(metrics_path: Path):
    if metrics_path.exists() and metrics_path.stat().st_size:
        try:
            metrics = pd.read_csv(metrics_path)
        except Exception:
            metrics = pd.DataFrame(columns=INPUT_COLUMNS)
    else:
        metrics = pd.DataFrame(columns=INPUT_COLUMNS)
    for col in INPUT_COLUMNS:
        if col not in metrics.columns:
            metrics[col] = pd.NA
    return metrics[INPUT_COLUMNS].copy()


def apply_fundamental_filter(
    candidates: pd.DataFrame,
    asof_date,
    metrics_path: str | Path = METRICS_PATH,
    thresholds_path: str | Path = THRESHOLDS_PATH,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Enrich every candidate with available fundamentals; never remove a row.

    `thresholds_path` remains in the signature for backward compatibility but
    is deliberately not used to reject candidates at the data-collection stage.
    Returns (enriched candidates, audit report).
    """
    del thresholds_path  # thresholds are reserved for a future shortlist stage
    metrics = _load_inputs(Path(metrics_path))
    output = candidates.copy()
    if "TckrSymb" not in output.columns:
        output["TckrSymb"] = pd.Series(dtype="object")
    output["TckrSymb"] = output["TckrSymb"].astype(str).str.strip().str.upper()

    metrics["TckrSymb"] = metrics["TckrSymb"].astype(str).str.strip().str.upper()
    counts = metrics["TckrSymb"].value_counts() if not metrics.empty else pd.Series(dtype=int)
    duplicates = set(counts[counts > 1].index)
    metric_rows = {
        str(row["TckrSymb"]): row
        for _, row in metrics.iterrows()
        if str(row["TckrSymb"]).strip() and str(row["TckrSymb"]).lower() != "nan"
    }

    enriched_rows = []
    for _, candidate in output.iterrows():
        row = candidate.to_dict()
        symbol = str(row.get("TckrSymb", "")).strip().upper()
        financial = metric_rows.get(symbol)
        reasons = []
        if symbol in duplicates:
            reasons.append("DUPLICATE_FUNDAMENTAL_RECORDS")
        if financial is None:
            reasons.append("FUNDAMENTAL_RECORD_MISSING")
        else:
            for col in INPUT_COLUMNS:
                row[col] = financial.get(col, pd.NA)
            missing_metrics = [col for col in METRIC_COLUMNS if not _nonempty(financial.get(col, pd.NA))]
            if missing_metrics:
                reasons.append("MISSING_METRICS:" + ",".join(missing_metrics))
            source_name = str(financial.get("Source", "")).strip()
            if not source_name or source_name.lower() == "nan":
                reasons.append("SOURCE_NAME_MISSING")
            source_url = str(financial.get("SourceURL", "")).strip()
            if not source_url or source_url.lower() == "nan":
                reasons.append("SOURCE_URL_MISSING")
            else:
                parsed = urlparse(source_url)
                if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                    reasons.append("INVALID_SOURCE_URL")
            asof = pd.to_datetime(asof_date, errors="coerce")
            period_end = pd.to_datetime(financial.get("FinancialPeriodEnd"), errors="coerce")
            publication_date = pd.to_datetime(financial.get("PublicationDate"), errors="coerce")
            publication_status = str(financial.get("PublicationDateStatus", "UNVERIFIED")).strip().upper()
            alignment_status = str(financial.get("MetricPeriodAlignmentStatus", "UNVERIFIED")).strip().upper()
            if pd.isna(period_end):
                reasons.append("FINANCIAL_PERIOD_END_UNVERIFIED")
            elif pd.notna(asof) and period_end.normalize() > asof.normalize():
                reasons.append("FINANCIAL_PERIOD_END_AFTER_EOD")
            if publication_status != "VERIFIED" or pd.isna(publication_date):
                reasons.append("PUBLICATION_DATE_UNVERIFIED")
            elif pd.notna(asof) and publication_date.normalize() > asof.normalize():
                reasons.append("PUBLICATION_DATE_AFTER_EOD")
            if alignment_status != "VERIFIED":
                reasons.append("METRIC_PERIOD_ALIGNMENT_UNVERIFIED")
            report_date = pd.to_datetime(financial.get("AsOfDate"), errors="coerce")
            if pd.notna(report_date) and pd.notna(asof) and report_date.normalize() > asof.normalize():
                reasons.append("FUNDAMENTAL_AS_OF_DATE_AFTER_EOD")

        supplied_count = sum(_nonempty(row.get(col, pd.NA)) for col in METRIC_COLUMNS)
        score_count = sum(_nonempty(row.get(col, pd.NA)) and pd.notna(_number(row.get(col))) for col in SCORE_METRICS)
        row["FundamentalMetricsCompletenessPct"] = round(supplied_count / len(METRIC_COLUMNS) * 100, 2)
        row["FundamentalScoreCoveragePct"] = round(score_count / len(SCORE_METRICS) * 100, 2)
        if financial is None or supplied_count == 0:
            status = "MISSING_DATA"
        elif supplied_count < len(METRIC_COLUMNS) or reasons:
            status = "PARTIAL_DATA"
        else:
            status = "COMPLETE"
        row["FundamentalStatus"] = status
        row["FundamentalAssessmentStatus"] = "NOT_SHORTLISTED_YET"
        row["FundamentalReason"] = ";".join(reasons) if reasons else "FUNDAMENTAL_DATA_COLLECTED_FOR_LATER_RANKING"
        row["FundamentalAsOfDate"] = row.get("AsOfDate", pd.NA)
        row["FundamentalSource"] = row.get("Source", pd.NA)
        row["FundamentalSourceURL"] = row.get("SourceURL", pd.NA)
        row["FundamentalPublicationDateStatus"] = row.get("PublicationDateStatus", "UNVERIFIED")
        row["FundamentalFinancialPeriodEnd"] = row.get("FinancialPeriodEnd", pd.NA)
        enriched_rows.append(row)

    audit = pd.DataFrame(enriched_rows)
    for col in STATUS_COLUMNS + METRIC_COLUMNS + SOURCE_COLUMNS:
        if col not in audit.columns:
            audit[col] = pd.NA

    # A score is produced only when all six numeric ranking metrics are present.
    # This prevents incomplete records from receiving misleading high ranks.
    score_parts = []
    for metric, higher_is_better in SCORE_METRICS.items():
        values = pd.to_numeric(audit.get(metric, pd.Series(index=audit.index, dtype=float)), errors="coerce")
        score_parts.append((values.rank(pct=True, ascending=higher_is_better) * 100.0).rename(metric + "PercentileScore"))
    score_frame = pd.concat(score_parts, axis=1) if score_parts else pd.DataFrame(index=audit.index)
    audit = pd.concat([audit, score_frame], axis=1)
    complete_score = audit["FundamentalScoreCoveragePct"].eq(100)
    publication_verified = audit.get("PublicationDateStatus", pd.Series("UNVERIFIED", index=audit.index)).astype(str).str.upper().eq("VERIFIED")
    alignment_verified = audit.get("MetricPeriodAlignmentStatus", pd.Series("UNVERIFIED", index=audit.index)).astype(str).str.upper().eq("VERIFIED")
    period_end = pd.to_datetime(audit.get("FinancialPeriodEnd", pd.Series(pd.NA, index=audit.index)), errors="coerce")
    publication_date = pd.to_datetime(audit.get("PublicationDate", pd.Series(pd.NA, index=audit.index)), errors="coerce")
    eod_cutoff = pd.to_datetime(asof_date, errors="coerce")
    point_in_time_valid = period_end.notna() & publication_date.notna()
    if pd.notna(eod_cutoff):
        point_in_time_valid &= period_end.dt.normalize().le(eod_cutoff.normalize())
        point_in_time_valid &= publication_date.dt.normalize().le(eod_cutoff.normalize())
    score_eligible = complete_score & publication_verified & alignment_verified & point_in_time_valid
    audit["FundamentalScore"] = score_frame.mean(axis=1, skipna=False).where(score_eligible).round(2)
    audit["FundamentalRank"] = audit["FundamentalScore"].rank(method="min", ascending=False).astype("Int64")
    audit["FundamentalScoreMethod"] = "Equal-weight percentile mean; only when six numeric metrics, official publication date, period end, and metric-period alignment are verified point-in-time"

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    audit.to_csv(OUTPUT_DIR / "v8_fundamental_report.csv", index=False)
    audit[audit["FundamentalStatus"] == "COMPLETE"].to_csv(OUTPUT_DIR / "v8_fundamental_complete_data.csv", index=False)
    audit[audit["FundamentalStatus"] == "PARTIAL_DATA"].to_csv(OUTPUT_DIR / "v8_fundamental_partial_data.csv", index=False)
    audit[audit["FundamentalStatus"] == "MISSING_DATA"].to_csv(OUTPUT_DIR / "v8_fundamental_missing_data.csv", index=False)
    return audit.copy(), audit.copy()
