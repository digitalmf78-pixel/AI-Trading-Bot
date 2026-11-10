"""Observational full-Mainboard cohort assembly for NSE V8.

This helper is deliberately not wired into scanner selection or trading gates.
The caller must pass the already-filtered Main Board candidate frame produced
by the existing official Main Board classifier. Stage reports are left-joined
onto that fixed cohort; absent rows never become PASS or REJECT.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
import re

import pandas as pd

SYMBOL_COLUMN = "TckrSymb"
class CohortAssemblyError(ValueError):
    """Raised when cohort identity or source report rows are ambiguous."""


@dataclass(frozen=True)
class CohortAssemblyResult:
    cohort: pd.DataFrame
    news_evidence: pd.DataFrame
    corporate_event_evidence: pd.DataFrame
    diagnostics: pd.DataFrame


def _normalise_symbol(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip().upper()


def _keyed(frame: pd.DataFrame, label: str) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        raise CohortAssemblyError(f"{label}: expected a pandas DataFrame")
    if SYMBOL_COLUMN not in frame.columns:
        raise CohortAssemblyError(f"{label}: missing required {SYMBOL_COLUMN} column")
    if not frame.columns.is_unique:
        duplicates = frame.columns[frame.columns.duplicated()].astype(str).unique().tolist()
        raise CohortAssemblyError(f"{label}: duplicate column names are ambiguous: {duplicates[:20]}")
    reserved = {"_cohort_symbol_key", "_cohort_series_key"}
    collisions = sorted(reserved.intersection(map(str, frame.columns)))
    if collisions:
        raise CohortAssemblyError(f"{label}: reserved internal columns supplied by source: {collisions}")
    out = frame.copy()
    out["_cohort_symbol_key"] = out[SYMBOL_COLUMN].map(_normalise_symbol)
    if (out["_cohort_symbol_key"] == "").any():
        raise CohortAssemblyError(f"{label}: blank/null symbol key")
    duplicates = sorted(out.loc[out["_cohort_symbol_key"].duplicated(keep=False), "_cohort_symbol_key"].unique())
    if duplicates:
        raise CohortAssemblyError(f"{label}: duplicate symbol keys are ambiguous: {duplicates[:20]}")
    if "SctySrs" in out.columns:
        out["_cohort_series_key"] = out["SctySrs"].map(
            lambda value: "" if pd.isna(value) else str(value).strip().upper()
        )
        if (out["_cohort_series_key"] == "").any():
            raise CohortAssemblyError(f"{label}: blank/null SctySrs for a symbol-keyed row")
    return out


def _validate_series_alignment(base: pd.DataFrame, report: pd.DataFrame, label: str) -> None:
    base_has_series = "_cohort_series_key" in base.columns
    report_has_series = "_cohort_series_key" in report.columns
    if not base_has_series or not report_has_series:
        return
    aligned = base[["_cohort_symbol_key", "_cohort_series_key"]].merge(
        report[["_cohort_symbol_key", "_cohort_series_key"]],
        on="_cohort_symbol_key", how="inner", suffixes=("_base", "_report"),
        validate="one_to_one",
    )
    mismatch = aligned[
        aligned["_cohort_series_key_base"] != aligned["_cohort_series_key_report"]
    ]
    if not mismatch.empty:
        sample = mismatch.head(20).to_dict("records")
        raise CohortAssemblyError(
            f"{label}: SctySrs mismatch for matching symbols: {sample}"
        )


def assemble_mainboard_cohort(
    mainboard_candidates: pd.DataFrame,
    *,
    reports: Mapping[str, pd.DataFrame | None] | None = None,
    news_report: pd.DataFrame | None = None,
    corporate_events_report: pd.DataFrame | None = None,
) -> CohortAssemblyResult:
    """Left-join stage evidence onto every official Main Board candidate.

    The production scanner currently deduplicates the prepared equity frame by
    TckrSymb before official Main Board classification. Accordingly this
    observational cohort uses symbol as its identity key and rejects duplicate
    symbols rather than silently choosing a series or row. A future change to
    scanner identity must update this contract and tests explicitly.
    """
    base = _keyed(mainboard_candidates, "mainboard_candidates")
    generated_base_columns = {
        "CohortEligibilityStatus", "CohortIdentityKey",
        "DownstreamReportsPresent", "DownstreamReportsExpected",
    }
    base_collisions = sorted(generated_base_columns.intersection(map(str, base.columns)))
    if base_collisions:
        raise CohortAssemblyError(f"mainboard_candidates: source columns collide with generated fields: {base_collisions}")
    # Preserve source columns untouched; only the internal key is removed at end.
    base["CohortEligibilityStatus"] = "PASS_MAIN_BOARD_INPUT"
    base["CohortIdentityKey"] = base["_cohort_symbol_key"]
    diagnostics: list[dict] = []

    seen_stage_names: set[str] = set()
    for stage, report in (reports or {}).items():
        safe_stage = str(stage).strip()
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", safe_stage):
            raise CohortAssemblyError(f"Invalid stage name {stage!r}; use letters, digits, and underscores")
        if safe_stage in seen_stage_names:
            raise CohortAssemblyError(f"Duplicate stage name after normalization: {safe_stage}")
        seen_stage_names.add(safe_stage)
        coverage_col = f"{safe_stage}__CoverageStatus"
        generated_stage_columns = {coverage_col, f"{safe_stage}__CoverageReason"}
        stage_collisions = sorted(generated_stage_columns.intersection(map(str, base.columns)))
        if stage_collisions:
            raise CohortAssemblyError(
                f"{safe_stage}: generated output columns collide with existing cohort columns: {stage_collisions}"
            )
        if report is None:
            base[coverage_col] = "NOT_EVALUATED"
            base[f"{safe_stage}__CoverageReason"] = "SOURCE_REPORT_NOT_SUPPLIED"
            diagnostics.append({"Stage": safe_stage, "Diagnostic": "SOURCE_REPORT_NOT_SUPPLIED", "Rows": 0})
            continue
        if not isinstance(report, pd.DataFrame):
            raise CohortAssemblyError(f"{safe_stage}: report must be a DataFrame or None")
        if report.empty:
            if not report.columns.is_unique:
                duplicates = report.columns[report.columns.duplicated()].astype(str).unique().tolist()
                raise CohortAssemblyError(f"{safe_stage}: duplicate column names are ambiguous: {duplicates[:20]}")
            reserved_report_columns = {"_cohort_symbol_key", "_cohort_series_key"}
            reserved_collisions = sorted(reserved_report_columns.intersection(map(str, report.columns)))
            if reserved_collisions:
                raise CohortAssemblyError(f"{safe_stage}: reserved internal columns supplied by source: {reserved_collisions}")
            base[coverage_col] = "NOT_EVALUATED"
            base[f"{safe_stage}__CoverageReason"] = "SOURCE_REPORT_EMPTY"
            diagnostics.append({"Stage": safe_stage, "Diagnostic": "SOURCE_REPORT_EMPTY", "Rows": 0})
            continue

        keyed_report = _keyed(report, safe_stage)
        _validate_series_alignment(base, keyed_report, safe_stage)
        report_symbols = set(keyed_report["_cohort_symbol_key"])
        base_symbols = set(base["_cohort_symbol_key"])
        matched = base_symbols & report_symbols
        extras = report_symbols - base_symbols
        series_alignment = (
            "VERIFIED_MATCH" if "_cohort_series_key" in base.columns and "_cohort_series_key" in keyed_report.columns
            else "NOT_CHECKED_SERIES_MISSING_IN_BASE" if "_cohort_series_key" not in base.columns
            else "NOT_CHECKED_SERIES_MISSING_IN_REPORT"
        )
        diagnostics.append({
            "Stage": safe_stage,
            "Diagnostic": "LEFT_JOIN_COVERAGE",
            "SeriesAlignmentStatus": series_alignment,
            "Rows": len(keyed_report),
            "MatchedCohortRows": len(matched),
            "MissingCohortRows": len(base_symbols - report_symbols),
            "OutOfCohortRows": len(extras),
        })

        payload_columns = [c for c in keyed_report.columns if c not in {"_cohort_symbol_key", "_cohort_series_key"}]
        renamed = keyed_report[["_cohort_symbol_key"] + payload_columns].rename(
            columns={c: f"{safe_stage}__{c}" for c in payload_columns}
        )
        generated_names = set(renamed.columns) - {"_cohort_symbol_key"}
        generated_names.update({coverage_col, f"{safe_stage}__CoverageReason"})
        output_collisions = sorted(generated_names.intersection(map(str, base.columns)))
        if output_collisions:
            raise CohortAssemblyError(
                f"{safe_stage}: generated output columns collide with existing cohort columns: {output_collisions[:20]}"
            )
        base = base.merge(renamed, on="_cohort_symbol_key", how="left", validate="one_to_one", sort=False)
        matched_mask = base["_cohort_symbol_key"].isin(matched)
        base[coverage_col] = "SOURCE_ROW_PRESENT"
        base.loc[~matched_mask, coverage_col] = "NOT_EVALUATED"
        base[f"{safe_stage}__CoverageReason"] = ""
        base.loc[~matched_mask, f"{safe_stage}__CoverageReason"] = "MISSING_SOURCE_ROW"
        # Do not synthesize or reinterpret native status fields. The raw status
        # survives under <stage>__<original-column> exactly as supplied.

    def _one_to_many_evidence(report: pd.DataFrame | None, label: str) -> pd.DataFrame:
        coverage_column = f"{label}EvidenceCoverageStatus"
        if report is None:
            diagnostics.append({"Stage": label.lower() + "_evidence", "Diagnostic": "SOURCE_REPORT_NOT_SUPPLIED", "Rows": 0})
            return pd.DataFrame(columns=[SYMBOL_COLUMN, coverage_column])
        if not isinstance(report, pd.DataFrame):
            raise CohortAssemblyError(f"{label.lower()}_report: expected a pandas DataFrame or None")
        if report.empty:
            if not report.columns.is_unique:
                duplicates = report.columns[report.columns.duplicated()].astype(str).unique().tolist()
                raise CohortAssemblyError(f"{label.lower()}_report: duplicate column names are ambiguous: {duplicates[:20]}")
            if coverage_column in report.columns:
                raise CohortAssemblyError(f"{label.lower()}_report: reserved coverage column already exists: {coverage_column}")
            if "_cohort_symbol_key" in report.columns or "_cohort_series_key" in report.columns:
                raise CohortAssemblyError(f"{label.lower()}_report: source uses reserved internal cohort columns")
            empty = report.copy()
            if SYMBOL_COLUMN not in empty.columns:
                empty[SYMBOL_COLUMN] = pd.Series(dtype="object")
            empty[coverage_column] = pd.Series(dtype="object")
            diagnostics.append({"Stage": label.lower() + "_evidence", "Diagnostic": "SOURCE_REPORT_EMPTY", "Rows": 0})
            return empty
        if SYMBOL_COLUMN not in report.columns:
            raise CohortAssemblyError(f"{label.lower()}_report: missing required {SYMBOL_COLUMN} column")
        if not report.columns.is_unique:
            duplicates = report.columns[report.columns.duplicated()].astype(str).unique().tolist()
            raise CohortAssemblyError(f"{label.lower()}_report: duplicate column names are ambiguous: {duplicates[:20]}")
        if coverage_column in report.columns:
            raise CohortAssemblyError(f"{label.lower()}_report: reserved coverage column already exists: {coverage_column}")
        if "_cohort_symbol_key" in report.columns or "_cohort_series_key" in report.columns:
            raise CohortAssemblyError(f"{label.lower()}_report: source uses reserved internal cohort columns")
        evidence = report.copy()
        evidence["_cohort_symbol_key"] = evidence[SYMBOL_COLUMN].map(_normalise_symbol)
        if (evidence["_cohort_symbol_key"] == "").any():
            raise CohortAssemblyError(f"{label.lower()}_report: blank/null symbol key")
        cohort_symbols = set(base["_cohort_symbol_key"])
        if "_cohort_series_key" in base.columns:
            if "SctySrs" not in evidence.columns:
                diagnostics.append({
                    "Stage": label.lower() + "_evidence",
                    "Diagnostic": "SERIES_ALIGNMENT_NOT_CHECKED_SERIES_MISSING_IN_REPORT",
                    "Rows": len(evidence),
                })
            else:
                evidence["_cohort_series_key"] = evidence["SctySrs"].map(
                    lambda value: "" if pd.isna(value) else str(value).strip().upper()
                )
                if (evidence["_cohort_series_key"] == "").any():
                    raise CohortAssemblyError(f"{label.lower()}_report: blank/null SctySrs")
                series_map = base.set_index("_cohort_symbol_key")["_cohort_series_key"].to_dict()
                mismatch = evidence[
                    evidence["_cohort_symbol_key"].isin(cohort_symbols)
                    & evidence.apply(
                        lambda row: row["_cohort_series_key"] != series_map[row["_cohort_symbol_key"]], axis=1
                    )
                ]
                if not mismatch.empty:
                    raise CohortAssemblyError(
                        f"{label.lower()}_report: SctySrs mismatch for evidence rows: "
                        f"{mismatch[[SYMBOL_COLUMN, 'SctySrs']].head(20).to_dict('records')}"
                    )
        evidence[coverage_column] = evidence["_cohort_symbol_key"].map(
            lambda key: "SOURCE_ROW_PRESENT" if key in cohort_symbols else "OUT_OF_COHORT"
        )
        evidence = evidence.drop(columns=["_cohort_symbol_key"])
        diagnostics.append({
            "Stage": label.lower() + "_evidence",
            "Diagnostic": "ONE_TO_MANY_EVIDENCE_PRESERVED",
            "Rows": len(evidence),
            "MatchedEvidenceRows": int(evidence[coverage_column].eq("SOURCE_ROW_PRESENT").sum()),
            "OutOfCohortRows": int(evidence[coverage_column].eq("OUT_OF_COHORT").sum()),
        })
        return evidence

    news = _one_to_many_evidence(news_report, "News")
    corporate_events = _one_to_many_evidence(corporate_events_report, "CorporateEvent")

    # Explicit row-level coverage summary. No downstream status is used to filter.
    stage_coverage = [c for c in base.columns if c.endswith("__CoverageStatus")]
    base["DownstreamReportsPresent"] = base[stage_coverage].eq("SOURCE_ROW_PRESENT").sum(axis=1) if stage_coverage else 0
    base["DownstreamReportsExpected"] = len(stage_coverage)
    base = base.drop(columns=["_cohort_symbol_key", "_cohort_series_key"], errors="ignore")
    return CohortAssemblyResult(
        cohort=base.reset_index(drop=True),
        news_evidence=news.reset_index(drop=True),
        corporate_event_evidence=corporate_events.reset_index(drop=True),
        diagnostics=pd.DataFrame(diagnostics),
    )
