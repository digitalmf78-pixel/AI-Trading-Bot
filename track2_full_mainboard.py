"""Independent, non-gating Track 2 research report over the full Mainboard cohort.

This orchestration is intentionally NOT wired into the production scanner.
It reuses existing observation engines, writes to a separate artifact
namespace, and never changes Track 1 candidate eligibility or ranking.
"""
from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import re

import pandas as pd

from delivery_quantity_analysis import build_delivery_quantity_report
from potential_accumulation_analysis import build_potential_accumulation_report
from vcp_observation_analysis import build_vcp_observation_report


DEFAULT_OUTPUT_DIR = Path("outputs/track2_full_mainboard")
OBSERVER_SPECS = (
    ("delivery_quantity", "Track2DeliveryQuantityObserverStatus", "DeliveryQuantityStatus"),
    ("potential_accumulation", "Track2PotentialAccumulationObserverStatus", "EvidenceStatus"),
    ("vcp", "Track2VCPObserverStatus", "VCPObservationStatus"),
)


def _asof(value) -> date:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        raise ValueError(f"Invalid as-of date: {value!r}")
    return parsed.date()


def _symbol(value) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip().upper()


def _empty_status(value: str) -> str:
    return value if value else "WAIT_FOR_DATA"


def _safe_report(report, expected_symbols: set[str], symbol_col: str = "TckrSymb") -> pd.DataFrame:
    if report is None:
        raise ValueError("Observer returned None")
    if not isinstance(report, pd.DataFrame):
        raise TypeError("Observer must return a DataFrame")
    if report.empty:
        return pd.DataFrame(columns=[symbol_col])
    if symbol_col not in report.columns:
        raise ValueError(f"Observer output missing {symbol_col}")
    result = report.copy()
    result["_TRACK2_SYMBOL"] = result[symbol_col].map(_symbol)
    if result["_TRACK2_SYMBOL"].eq("").any():
        raise ValueError("Observer returned an invalid symbol key")
    if result["_TRACK2_SYMBOL"].duplicated().any():
        raise ValueError("Observer returned duplicate symbol keys")
    unexpected = set(result["_TRACK2_SYMBOL"]) - expected_symbols
    if unexpected:
        raise ValueError(f"Observer returned out-of-cohort symbols: {sorted(unexpected)[:5]}")
    return result.drop(columns=[symbol_col]).rename(columns={"_TRACK2_SYMBOL": symbol_col})


def _left_join_observer(base: pd.DataFrame, report: pd.DataFrame, status_col: str,
                        native_status_col: str) -> pd.DataFrame:
    if report.empty:
        base[status_col] = "WAIT_FOR_DATA"
        return base
    report = report.copy()
    if native_status_col in report.columns:
        report[status_col] = report[native_status_col].map(
            lambda value: _empty_status(str(value).strip()) if pd.notna(value) else "WAIT_FOR_DATA"
        )
    else:
        report[status_col] = "WAIT_FOR_DATA"
    overlap = (set(base.columns) & set(report.columns)) - {"TckrSymb", status_col}
    # Source cohort columns are authoritative; observer output may only enrich.
    report = report.drop(columns=sorted(overlap), errors="ignore")
    merged = base.drop(columns=[status_col], errors="ignore").merge(
        report, on="TckrSymb", how="left", validate="one_to_one", sort=False
    )
    merged[status_col] = merged[status_col].fillna("WAIT_FOR_DATA")
    return merged


def build_track2_full_mainboard_report(
    mainboard_candidates: pd.DataFrame,
    historical,
    delivery_sessions,
    asof_date,
    output_dir: str | Path | None = None,
    research_pattern_requested: str = "BOTH",
) -> tuple[pd.DataFrame, dict]:
    """Build separate full-Mainboard observations; never classify or gate patterns.

    The caller must pass the frame returned by the official Mainboard filter,
    before Delivery A/B selection. A MainBoardStatus column, when present, is
    independently checked for PASS_MAIN_BOARD; absence remains a documented
    caller assertion, not a re-verification of NSE membership.
    """
    asof = _asof(asof_date)
    requested = str(research_pattern_requested).strip().upper()
    if requested not in {"BOTH", "SIDEWAYS_ACCUMULATION", "DIP_ACCUMULATION"}:
        raise ValueError("research_pattern_requested must be BOTH, SIDEWAYS_ACCUMULATION, or DIP_ACCUMULATION")

    source = mainboard_candidates.copy() if isinstance(mainboard_candidates, pd.DataFrame) else pd.DataFrame()
    if not source.empty and "TckrSymb" not in source.columns:
        raise ValueError("Full Mainboard input requires TckrSymb")

    out_dir = Path(output_dir) if output_dir is not None else DEFAULT_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = asof.strftime("%Y%m%d")
    output_path = out_dir / f"v8_track2_full_mainboard_cohort_{stamp}.csv"

    if source.empty:
        empty = pd.DataFrame(columns=["TckrSymb", "AsOfDate", "Track2CohortStatus",
                                      "ResearchPatternRequested", "ResearchPatternStatus"])
        empty.to_csv(output_path, index=False)
        manifest = {
            "as_of_date": asof.isoformat(), "expected_input_rows": 0,
            "unique_valid_symbols": 0, "duplicate_symbol_count": 0,
            "invalid_symbol_row_count": 0, "output_rows": 0,
            "cohort_status": "EMPTY_INPUT", "observers": {},
        }
        (out_dir / f"v8_track2_coverage_manifest_{stamp}.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        return empty, manifest

    source = source.reset_index(drop=True)
    source["_TRACK2_SYMBOL"] = source["TckrSymb"].map(_symbol)
    valid_mask = source["_TRACK2_SYMBOL"].ne("")
    duplicate_mask = valid_mask & source["_TRACK2_SYMBOL"].duplicated(keep=False)
    duplicate_symbols = set(source.loc[duplicate_mask, "_TRACK2_SYMBOL"])

    # One output row per valid symbol; repeated identities are retained once
    # and explicitly fail closed. Invalid-key rows remain individually visible.
    rows = []
    seen = set()
    invalid_count = 0
    for index, raw in source.iterrows():
        symbol = raw["_TRACK2_SYMBOL"]
        if symbol:
            if symbol in seen:
                continue
            seen.add(symbol)
        else:
            invalid_count += 1
        record = raw.drop(labels=["_TRACK2_SYMBOL"]).to_dict()
        record["TckrSymb"] = symbol
        record["AsOfDate"] = asof.isoformat()
        record["ResearchPatternRequested"] = requested
        record["ResearchPatternStatus"] = (
            "NOT_CLASSIFIED_PENDING_APPROVED_RULES" if symbol else "WAIT_FOR_DATA"
        )
        record["ResearchPatternReason"] = (
            "NO_APPROVED_SIDEWAYS_OR_DIP_CLASSIFICATION_RULES" if symbol else "INVALID_SYMBOL_IDENTITY"
        )
        if not symbol:
            record["Track2CohortStatus"] = "WAIT_FOR_DATA"
            record["Track2CohortReason"] = "INVALID_SYMBOL_IDENTITY"
        elif symbol in duplicate_symbols:
            record["Track2CohortStatus"] = "WAIT_FOR_DATA"
            record["Track2CohortReason"] = "DUPLICATE_COHORT_SYMBOL"
        else:
            board_status = str(record.get("MainBoardStatus", "PASS_MAIN_BOARD")).strip().upper()
            board_class = str(record.get("BoardClassification", "MAIN_BOARD")).strip().upper()
            if board_status != "PASS_MAIN_BOARD" or board_class not in {"MAIN_BOARD", "NAN", ""}:
                record["Track2CohortStatus"] = "WAIT_FOR_DATA"
                record["Track2CohortReason"] = "INPUT_NOT_VERIFIED_AS_MAIN_BOARD"
            else:
                record["Track2CohortStatus"] = "PASS_MAIN_BOARD_INPUT"
                record["Track2CohortReason"] = "OFFICIAL_FILTERED_INPUT_CALLER_ASSERTION"
        for _, status_col, _ in OBSERVER_SPECS:
            record[status_col] = "WAIT_FOR_DATA"
        rows.append(record)

    base = pd.DataFrame(rows)
    eligible_symbols = set(
        base.loc[
            base["Track2CohortStatus"].eq("PASS_MAIN_BOARD_INPUT")
            & base["TckrSymb"].astype(str).ne(""),
            "TckrSymb",
        ].map(_symbol)
    )
    eligible_source = source.loc[source["_TRACK2_SYMBOL"].isin(eligible_symbols)].copy()
    eligible = eligible_source.drop(columns=["_TRACK2_SYMBOL"]).copy()
    eligible["TckrSymb"] = eligible_source["_TRACK2_SYMBOL"].values

    observer_errors = {}
    reports = {}
    observer_paths = {
        "delivery_quantity": out_dir / f"v8_track2_delivery_quantity_observations_{stamp}.csv",
        "potential_accumulation": out_dir / f"v8_track2_potential_accumulation_observations_{stamp}.csv",
        "vcp": out_dir / f"v8_track2_vcp_observations_{stamp}.csv",
    }
    # Avoid treating a stale same-day observer artifact as output from this run.
    for stale_path in observer_paths.values():
        if stale_path.exists():
            stale_path.unlink()

    if eligible_symbols:
        try:
            result, _ = build_delivery_quantity_report(
                eligible, asof, delivery_sessions,
                output_path=observer_paths["delivery_quantity"],
            )
            reports["delivery_quantity"] = _safe_report(result, eligible_symbols)
        except Exception as exc:
            observer_errors["delivery_quantity"] = f"{type(exc).__name__}:{exc}"
            reports["delivery_quantity"] = pd.DataFrame()
        try:
            result = build_potential_accumulation_report(
                eligible, historical, delivery_sessions, asof,
                output_path=observer_paths["potential_accumulation"],
            )
            reports["potential_accumulation"] = _safe_report(result, eligible_symbols)
        except Exception as exc:
            observer_errors["potential_accumulation"] = f"{type(exc).__name__}:{exc}"
            reports["potential_accumulation"] = pd.DataFrame()
        try:
            result = build_vcp_observation_report(
                eligible, historical, asof,
                output_path=observer_paths["vcp"],
            )
            reports["vcp"] = _safe_report(result, eligible_symbols)
        except Exception as exc:
            observer_errors["vcp"] = f"{type(exc).__name__}:{exc}"
            reports["vcp"] = pd.DataFrame()
    else:
        reports = {name: pd.DataFrame() for name, _, _ in OBSERVER_SPECS}
        observer_errors = {name: "NO_ELIGIBLE_UNIQUE_MAINBOARD_SYMBOLS" for name, _, _ in OBSERVER_SPECS}

    for name, status_col, native_status_col in OBSERVER_SPECS:
        report = reports.get(name, pd.DataFrame())
        if report.empty:
            base[status_col] = base[status_col].fillna("WAIT_FOR_DATA")
            continue
        base = _left_join_observer(base, report, status_col, native_status_col)
        # Cohort rows outside the eligible Mainboard input remain WAIT.
        base.loc[~base["Track2CohortStatus"].eq("PASS_MAIN_BOARD_INPUT"), status_col] = "WAIT_FOR_DATA"

    base.to_csv(output_path, index=False)
    session_dates = sorted({
        pd.Timestamp(day).date().isoformat()
        for day, _ in (delivery_sessions or [])
        if pd.notna(pd.to_datetime(day, errors="coerce"))
        and pd.Timestamp(day).date() <= asof
    })
    observer_summary = {}
    for name, status_col, _ in OBSERVER_SPECS:
        observer_summary[name] = {
            "status_counts": base[status_col].value_counts(dropna=False).to_dict(),
            "error": observer_errors.get(name),
            "artifact": str(observer_paths[name]) if name in observer_paths and observer_paths[name].exists() else None,
        }
    manifest = {
        "as_of_date": asof.isoformat(),
        "expected_input_rows": int(len(source)),
        "unique_valid_symbols": int(source.loc[valid_mask, "_TRACK2_SYMBOL"].nunique()),
        "duplicate_symbol_count": int(len(duplicate_symbols)),
        "invalid_symbol_row_count": int(invalid_count),
        "eligible_unique_mainboard_symbols": int(len(eligible_symbols)),
        "output_rows": int(len(base)),
        "cohort_status": "COMPLETE" if not duplicate_symbols and invalid_count == 0 else "PARTIAL_INPUT_IDENTITY",
        "delivery_source_dates": session_dates,
        "research_pattern_requested": requested,
        "research_pattern_status": "NOT_CLASSIFIED_PENDING_APPROVED_RULES",
        "observers": observer_summary,
    }
    (out_dir / f"v8_track2_coverage_manifest_{stamp}.json").write_text(
        json.dumps(manifest, indent=2, default=str), encoding="utf-8"
    )
    return base, manifest
