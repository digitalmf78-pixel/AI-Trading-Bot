"""Evidence-first fundamental filter for NSE V8 EOD.

The filter never invents financial data or silently assumes thresholds. A stock
passes only when required metrics, source evidence, freshness policy, and all
configured thresholds are present. Missing inputs/configuration => WAIT_FOR_DATA.
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
SOURCE_COLUMNS = ["TckrSymb", "AsOfDate", "Source", "SourceURL"]
INPUT_COLUMNS = SOURCE_COLUMNS + METRIC_COLUMNS
THRESHOLD_KEYS = [
    "min_revenue_growth_pct", "min_profit_growth_pct", "min_roe_pct",
    "min_roce_pct", "max_debt_to_equity", "min_interest_coverage",
    "require_positive_operating_cash_flow", "require_positive_free_cash_flow",
    "acceptable_earnings_quality_status", "acceptable_valuation_status",
    "max_data_age_days",
]
STATUS_COLUMNS = [
    "FundamentalStatus", "FundamentalReason", "FundamentalAsOfDate",
    "FundamentalSource", "FundamentalSourceURL", "FundamentalMetricsCompletenessPct",
]


def create_fundamental_templates() -> None:
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if not METRICS_PATH.exists():
        pd.DataFrame(columns=INPUT_COLUMNS).to_csv(METRICS_PATH, index=False)
    if not THRESHOLDS_PATH.exists():
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


def _thresholds_ready(config: dict) -> tuple[bool, list[str]]:
    missing = []
    for key in THRESHOLD_KEYS:
        value = config.get(key)
        if value is None or value == "":
            missing.append(key)
    if not isinstance(config.get("require_positive_operating_cash_flow"), bool):
        if "require_positive_operating_cash_flow" not in missing:
            missing.append("require_positive_operating_cash_flow")
    if not isinstance(config.get("require_positive_free_cash_flow"), bool):
        if "require_positive_free_cash_flow" not in missing:
            missing.append("require_positive_free_cash_flow")
    for key in ("acceptable_earnings_quality_status", "acceptable_valuation_status"):
        if not isinstance(config.get(key), list) or not config.get(key):
            if key not in missing:
                missing.append(key)
    for key in ["min_revenue_growth_pct", "min_profit_growth_pct", "min_roe_pct", "min_roce_pct", "max_debt_to_equity", "min_interest_coverage", "max_data_age_days"]:
        if key not in missing:
            try:
                number = float(config[key])
                if not pd.notna(number):
                    missing.append("INVALID:" + key)
                elif key in {"max_debt_to_equity", "min_interest_coverage", "max_data_age_days"} and number < 0:
                    missing.append("INVALID:" + key)
            except (TypeError, ValueError):
                missing.append("INVALID:" + key)
    return not missing, missing


def _load_inputs(metrics_path: Path, thresholds_path: Path):
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
    if thresholds_path.exists():
        try:
            config = json.loads(thresholds_path.read_text(encoding="utf-8"))
        except Exception:
            config = {}
    else:
        config = {}
    return metrics[INPUT_COLUMNS].copy(), config


def apply_fundamental_filter(
    candidates: pd.DataFrame,
    asof_date,
    metrics_path: str | Path = METRICS_PATH,
    thresholds_path: str | Path = THRESHOLDS_PATH,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Annotate candidates and return (candidate frame, complete audit frame).

    This function does not remove rows. The caller must explicitly send only
    FundamentalStatus == PASS to ranking; retaining the audit rows is deliberate.
    """
    metrics_path, thresholds_path = Path(metrics_path), Path(thresholds_path)
    metrics, config = _load_inputs(metrics_path, thresholds_path)
    ready, missing_thresholds = _thresholds_ready(config)
    output = candidates.copy()
    if "TckrSymb" not in output.columns:
        output["TckrSymb"] = pd.Series(dtype="object")
    output["TckrSymb"] = output["TckrSymb"].astype(str).str.strip().str.upper()

    metric_rows = {}
    duplicates = set()
    if not metrics.empty:
        metrics["TckrSymb"] = metrics["TckrSymb"].astype(str).str.strip().str.upper()
        counts = metrics["TckrSymb"].value_counts()
        duplicates = set(counts[counts > 1].index)
        metric_rows = {
            str(row["TckrSymb"]): row
            for _, row in metrics.iterrows()
            if str(row["TckrSymb"]).strip()
        }

    enriched_rows = []
    asof = pd.to_datetime(asof_date, errors="coerce")
    for _, candidate in output.iterrows():
        symbol = str(candidate.get("TckrSymb", "")).strip().upper()
        row = candidate.to_dict()
        financial = metric_rows.get(symbol)
        reasons = []
        if symbol in duplicates:
            reasons.append("DUPLICATE_FUNDAMENTAL_RECORDS")
        if financial is None:
            reasons.append("FUNDAMENTAL_RECORD_MISSING")
        else:
            for col in INPUT_COLUMNS:
                if col in SOURCE_COLUMNS + METRIC_COLUMNS:
                    row[col] = financial.get(col, pd.NA)
            missing_fields = [col for col in INPUT_COLUMNS if not _nonempty(financial.get(col, pd.NA))]
            if missing_fields:
                reasons.append("MISSING_CRITICAL_FIELDS:" + ",".join(missing_fields))
            source_url = str(financial.get("SourceURL", "")).strip()
            if source_url:
                parsed = urlparse(source_url)
                if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                    reasons.append("INVALID_SOURCE_URL")
            report_date = pd.to_datetime(financial.get("AsOfDate"), errors="coerce")
            if pd.isna(report_date) or pd.isna(asof):
                reasons.append("INVALID_FINANCIAL_AS_OF_DATE")
            elif report_date.normalize() > asof.normalize():
                reasons.append("FINANCIAL_AS_OF_DATE_AFTER_EOD")
            elif ready and (asof.normalize() - report_date.normalize()).days > int(config["max_data_age_days"]):
                reasons.append("FUNDAMENTAL_DATA_STALE")

        if not ready:
            reasons.append("THRESHOLDS_NOT_CONFIGURED:" + ",".join(missing_thresholds))

        if financial is not None and not reasons:
            numeric_map = {
                "RevenueGrowthPct": "min_revenue_growth_pct",
                "ProfitGrowthPct": "min_profit_growth_pct",
                "ROEPercent": "min_roe_pct",
                "ROCEPercent": "min_roce_pct",
                "DebtToEquity": "max_debt_to_equity",
                "InterestCoverage": "min_interest_coverage",
            }
            for metric, threshold in numeric_map.items():
                value = _number(financial.get(metric))
                if pd.isna(value):
                    reasons.append("INVALID_NUMERIC:" + metric)
                elif threshold.startswith("min_") and value < float(config[threshold]):
                    reasons.append("THRESHOLD_FAIL:" + metric)
                elif threshold == "max_debt_to_equity" and value > float(config[threshold]):
                    reasons.append("THRESHOLD_FAIL:" + metric)
            for metric, key in [("OperatingCashFlowINR", "require_positive_operating_cash_flow"),
                                ("FreeCashFlowINR", "require_positive_free_cash_flow")]:
                value = _number(financial.get(metric))
                if pd.isna(value):
                    reasons.append("INVALID_NUMERIC:" + metric)
                elif config[key] and value <= 0:
                    reasons.append("THRESHOLD_FAIL:" + metric)
            if str(financial.get("EarningsQualityStatus", "")).strip().upper() not in {
                str(v).strip().upper() for v in config["acceptable_earnings_quality_status"]
            }:
                reasons.append("THRESHOLD_FAIL:EarningsQualityStatus")
            if str(financial.get("ValuationStatus", "")).strip().upper() not in {
                str(v).strip().upper() for v in config["acceptable_valuation_status"]
            }:
                reasons.append("THRESHOLD_FAIL:ValuationStatus")

        if any(reason.startswith("THRESHOLD_FAIL:") for reason in reasons):
            status = "REJECT"
        elif reasons:
            status = "WAIT_FOR_DATA"
        else:
            status = "PASS"

        supplied_count = sum(_nonempty(row.get(col, pd.NA)) for col in METRIC_COLUMNS)
        row["FundamentalStatus"] = status
        row["FundamentalReason"] = ";".join(reasons) if reasons else "ALL_CONFIGURED_FUNDAMENTAL_CHECKS_PASSED"
        row["FundamentalAsOfDate"] = row.get("AsOfDate", pd.NA)
        row["FundamentalSource"] = row.get("Source", pd.NA)
        row["FundamentalSourceURL"] = row.get("SourceURL", pd.NA)
        row["FundamentalMetricsCompletenessPct"] = round(supplied_count / len(METRIC_COLUMNS) * 100, 2)
        enriched_rows.append(row)

    audit = pd.DataFrame(enriched_rows)
    for col in STATUS_COLUMNS + METRIC_COLUMNS + SOURCE_COLUMNS:
        if col not in audit.columns:
            audit[col] = pd.NA

    # Transparent relative Fundamental Score (0-100), used for ranking only.
    # It does not override missing/stale evidence or configured PASS/REJECT gates.
    # Each available numeric metric contributes an in-universe percentile; higher
    # is better except DebtToEquity, where lower is better.
    score_metrics = {
        "RevenueGrowthPct": True,
        "ProfitGrowthPct": True,
        "ROEPercent": True,
        "ROCEPercent": True,
        "DebtToEquity": False,
        "InterestCoverage": True,
        "OperatingCashFlowINR": True,
        "FreeCashFlowINR": True,
    }
    metric_percentiles = []
    for metric, higher_is_better in score_metrics.items():
        values = pd.to_numeric(audit[metric], errors="coerce")
        ranks = values.rank(method="average", pct=True, ascending=higher_is_better)
        # For lower-is-better metrics, ascending=True makes the smallest value
        # rank lowest; invert to reward the smaller debt ratio.
        if not higher_is_better:
            ranks = 1.0 - ranks + (1.0 / max(int(values.notna().sum()), 1))
            ranks = ranks.clip(0, 1)
        metric_percentiles.append(ranks.rename(metric + "_Percentile"))
    if metric_percentiles:
        pct_frame = pd.concat(metric_percentiles, axis=1)
        audit["FundamentalScoreCompletenessPct"] = (
            pct_frame.notna().sum(axis=1) / len(score_metrics) * 100
        ).round(2)
        audit["FundamentalScore"] = (
            pct_frame.mean(axis=1, skipna=True) * 100
        ).round(2)
        audit.loc[pct_frame.notna().sum(axis=1) < 4, "FundamentalScore"] = pd.NA
    else:
        audit["FundamentalScoreCompletenessPct"] = 0.0
        audit["FundamentalScore"] = pd.NA
    audit["FundamentalRank"] = audit["FundamentalScore"].rank(
        method="min", ascending=False, na_option="bottom"
    ).astype("Int64")
    audit["FundamentalStrength"] = audit["FundamentalScore"].apply(
        lambda score: "SCORED_STRONGER_RELATIVE" if pd.notna(score) else "WAIT_FOR_DATA"
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    audit.to_csv(OUTPUT_DIR / "v8_fundamental_report.csv", index=False)
    audit[audit["FundamentalStatus"] == "PASS"].to_csv(OUTPUT_DIR / "v8_fundamental_passed.csv", index=False)
    audit[audit["FundamentalStatus"] == "REJECT"].to_csv(OUTPUT_DIR / "v8_fundamental_rejected.csv", index=False)
    audit[audit["FundamentalStatus"] == "WAIT_FOR_DATA"].to_csv(OUTPUT_DIR / "v8_fundamental_wait_for_data.csv", index=False)
    return audit.copy(), audit.copy()
