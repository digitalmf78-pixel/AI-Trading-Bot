"""Observation-only Mainboard cohort and immutable point-in-time snapshots."""
from __future__ import annotations

from pathlib import Path
import json

import pandas as pd

from signal_cohort_assembly import assemble_mainboard_cohort
from signal_shadow_store import (
    SAFE_SIGNAL_FIELDS, append_immutable_jsonl, build_signal_snapshot,
)

FIELD_SOURCES = {
    "Close": ("ClsPric",),
    "Open": ("OpnPric",),
    "High": ("HghPric",),
    "Low": ("LwPric",),
    "Volume": ("TtlTradgVol",),
    "TtlTrfVal": ("TtlTrfVal",),
    "SctySrs": ("SctySrs",),
    "RVOL": ("technical__RVOL",),
    "RVOLBand": ("technical__RVOLBand",),
    "RVOLThresholdStatus": ("technical__RVOLThresholdStatus",),
    "DeliverySessions": ("delivery__DeliverySessions",),
    "DeliveryExpectedSessions30D": ("delivery__DeliveryExpectedSessions30D",),
    "DeliveryCoveragePct": ("delivery__DeliveryCoveragePct",),
    "DeliveryDailyPassCount": ("delivery__DeliveryDailyPassCount",),
    "AvgDelivery30D": ("delivery__AvgDelivery30D",),
    "LatestDeliveryPct": ("delivery__LatestDeliveryPct",),
    "DeliveryCategoryAStatus": ("delivery__DeliveryCategoryAStatus",),
    "DeliveryCategoryBStatus": ("delivery__DeliveryCategoryBStatus",),
    "DeliveryFilterStatus": ("delivery__DeliveryFilterStatus",),
    "LiquiditySessions": ("liquidity__LiquiditySessions",),
    "AvgDailyTradedValue20D": ("liquidity__AvgDailyTradedValue20D",),
    "LiquidityStatus": ("liquidity__LiquidityStatus",),
    "LiquidityFilterStatus": ("liquidity__LiquidityFilterStatus",),
    "LiquidityTier": ("liquidity__LiquidityTier",),
    "FundamentalStatus": ("fundamental__FundamentalStatus",),
    "FundamentalReason": ("fundamental__FundamentalReason",),
    "CoreTechnicalScreenStatus": ("technical__CoreTechnicalScreenStatus",),
    "SetupType": ("technical__SetupType",),
    "RelativeStrengthNifty": ("technical__RelativeStrengthNifty",),
    "EntryZoneLow": ("technical__EntryZoneLow",),
    "EntryZoneHigh": ("technical__EntryZoneHigh",),
    "EntryPricePlan": ("final_eod__EntryPricePlan",),
    "StopLossPlan": ("final_eod__StopLossPlan",),
    "TargetPricePlan": ("final_eod__TargetPricePlan",),
    "TargetSource": ("final_eod__TargetSource",),
    "RiskReward": ("final_eod__RiskReward",),
    "RiskRewardStatus": ("final_eod__RiskRewardStatus",),
    "EODWatchlistStatus": ("final_eod__EODWatchlistStatus",),
    "EODWatchlistReason": ("final_eod__EODWatchlistReason",),
}


def _json_scalar(value):
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _signal_fields(row) -> dict:
    fields = {}
    for target, candidates in FIELD_SOURCES.items():
        if target not in SAFE_SIGNAL_FIELDS:
            continue
        for source in candidates:
            if source in row.index:
                value = _json_scalar(row[source])
                if value is not None and value != "":
                    fields[target] = value
                    break
    return fields


def build_mainboard_signal_shadow(
    mainboard_candidates: pd.DataFrame,
    *,
    reports: dict[str, pd.DataFrame | None],
    eod_date,
    strategy_version: str,
    output_dir: str | Path = "outputs/signal_shadow",
    workflow_run_id: str = "",
    workflow_run_attempt: str = "",
) -> dict:
    """Left-join existing stage evidence and write one point-in-time snapshot per Mainboard symbol."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    assembled = assemble_mainboard_cohort(mainboard_candidates, reports=reports)
    assembled.cohort.to_csv(output / "full_mainboard_cohort.csv", index=False)
    assembled.diagnostics.to_csv(output / "cohort_coverage_diagnostics.csv", index=False)
    assembled.news_evidence.to_csv(output / "news_evidence.csv", index=False)
    assembled.corporate_event_evidence.to_csv(output / "corporate_event_evidence.csv", index=False)

    records = []
    for _, row in assembled.cohort.iterrows():
        symbol = str(row.get("TckrSymb", "")).strip().upper()
        if not symbol:
            continue
        records.append(build_signal_snapshot(
            eod_date=eod_date,
            symbol=symbol,
            strategy_version=strategy_version,
            signal_fields=_signal_fields(row),
            workflow_run_id=workflow_run_id,
            workflow_run_attempt=workflow_run_attempt,
            run_mode="EOD",
            source_reports=tuple(sorted(reports)),
        ))
    snapshot_path = output / "snapshots.jsonl"
    stats = append_immutable_jsonl(
        snapshot_path, records, key_field="signal_id",
        hash_field="snapshot_payload_sha256",
    )
    manifest = {
        "EODDate": str(pd.Timestamp(eod_date).date()),
        "StrategyVersion": strategy_version,
        "MainboardCohortRows": len(assembled.cohort),
        "SnapshotRowsRequested": len(records),
        "SnapshotsAppended": stats["appended"],
        "ExactDuplicates": stats["duplicates"],
        "SnapshotSchemaVersion": records[0]["schema_version"] if records else "1.0",
        "ObservationOnly": True,
        "SelectionMutation": False,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
