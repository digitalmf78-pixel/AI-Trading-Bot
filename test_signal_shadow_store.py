from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from signal_shadow_store import (
    SignalConflictError,
    SignalStoreError,
    SignalValidationError,
    append_immutable_jsonl,
    build_signal_snapshot,
    build_stage_event,
)


SHA = "a" * 40


def snapshot(**overrides):
    values = dict(
        eod_date="2026-11-09",
        symbol="reliance",
        strategy_version=SHA,
        signal_fields={"Close": 1500.0, "RVOLBand": "HIGH_RVOL_GT_1_5"},
        workflow_run_id="100",
        workflow_run_attempt="2",
        run_mode="EOD",
        created_at_utc="2026-11-10T10:00:00+00:00",
        source_reports=["v8_delivery_dual_category_audit.csv"],
    )
    values.update(overrides)
    return build_signal_snapshot(**values)


def test_signal_id_and_payload_hash_ignore_runner_timestamp():
    first = snapshot(created_at_utc="2026-11-10T10:00:00+00:00")
    second = snapshot(created_at_utc="2026-11-10T11:00:00+00:00", workflow_run_id="101")
    assert first["signal_id"] == second["signal_id"]
    assert first["snapshot_payload_sha256"] == second["snapshot_payload_sha256"]
    assert first["CreatedAtUTC"] != second["CreatedAtUTC"]


def test_datetime_is_not_accepted_as_an_eod_date():
    with pytest.raises(SignalValidationError, match="not a datetime"):
        snapshot(eod_date=datetime(2026, 11, 9, 16, 0, tzinfo=timezone.utc))


def test_only_eod_mode_can_create_snapshots():
    with pytest.raises(SignalValidationError, match="Only EOD"):
        snapshot(run_mode="PREMARKET")


@pytest.mark.parametrize("fields", [
    {"RiskBudgetINR": 1000},
    {"ProposedPositionQty": 10},
    {"nested": {"api_token": "do-not-store"}},
    {"unmapped_field": "not approved"},
])
def test_sensitive_or_unapproved_fields_are_rejected(fields):
    with pytest.raises(SignalValidationError):
        snapshot(signal_fields=fields)


def test_non_finite_values_fail_closed():
    with pytest.raises(SignalValidationError):
        snapshot(signal_fields={"Close": float("nan")})


def test_stage_event_preserves_raw_status_and_is_deterministic():
    args = dict(
        signal_id="b" * 64, eod_date="2026-11-09", symbol="RELIANCE",
        strategy_version=SHA, stage_name="DELIVERY_30D_AB",
        status="FILTERED_OUT_AVG_LT_60_PERCENT",
        reason_code="AVG_BELOW_THRESHOLD", reason_text="Raw source reason",
        source_report="v8_delivery_dual_category_audit.csv",
        source_row_hash="c" * 64,
    )
    first = build_stage_event(**args, observed_at_utc="2026-11-10T10:00:00+00:00")
    second = build_stage_event(**args, observed_at_utc="2026-11-10T11:00:00+00:00")
    assert first["event_id"] == second["event_id"]
    assert first["Status"] == "FILTERED_OUT_AVG_LT_60_PERCENT"


def test_append_exact_duplicate_is_noop(tmp_path: Path):
    path = tmp_path / "snapshots" / "2026-11-09.jsonl"
    row = snapshot()
    assert append_immutable_jsonl(path, [row], key_field="signal_id",
                                  hash_field="snapshot_payload_sha256") == {
        "appended": 1, "duplicates": 0
    }
    before = path.read_text(encoding="utf-8")
    assert append_immutable_jsonl(path, [row], key_field="signal_id",
                                  hash_field="snapshot_payload_sha256") == {
        "appended": 0, "duplicates": 1
    }
    assert path.read_text(encoding="utf-8") == before
    assert len([json.loads(line) for line in before.splitlines()]) == 1


def test_changed_payload_conflicts_and_preserves_existing_record(tmp_path: Path):
    path = tmp_path / "2026-11-09.jsonl"
    original = snapshot()
    append_immutable_jsonl(path, [original], key_field="signal_id",
                           hash_field="snapshot_payload_sha256")
    changed = snapshot(signal_fields={"Close": 1501.0})
    with pytest.raises(SignalConflictError):
        append_immutable_jsonl(path, [changed], key_field="signal_id",
                               hash_field="snapshot_payload_sha256")
    stored = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert stored["signal_fields"]["Close"] == 1500.0


def test_caller_cannot_supply_a_false_snapshot_hash(tmp_path: Path):
    row = snapshot()
    row["snapshot_payload_sha256"] = "0" * 64
    with pytest.raises(SignalValidationError, match="hash mismatch"):
        append_immutable_jsonl(tmp_path / "bad.jsonl", [row], key_field="signal_id",
                               hash_field="snapshot_payload_sha256")
    assert not (tmp_path / "bad.jsonl").exists()


def test_existing_record_tampering_is_detected(tmp_path: Path):
    path = tmp_path / "tampered.jsonl"
    row = snapshot()
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    loaded["signal_fields"]["Close"] = 9999.0
    path.write_text(json.dumps(loaded) + "\n", encoding="utf-8")
    with pytest.raises(SignalStoreError, match="hash mismatch"):
        append_immutable_jsonl(path, [row], key_field="signal_id",
                               hash_field="snapshot_payload_sha256")


def test_conflicting_duplicates_inside_batch_fail(tmp_path: Path):
    path = tmp_path / "2026-11-09.jsonl"
    with pytest.raises(SignalConflictError):
        append_immutable_jsonl(
            path, [snapshot(), snapshot(signal_fields={"Close": 1600.0})],
            key_field="signal_id", hash_field="snapshot_payload_sha256",
        )
    assert not path.exists()


def test_append_batch_deduplicates_exact_repeats(tmp_path: Path):
    path = tmp_path / "2026-11-09.jsonl"
    row = snapshot()
    result = append_immutable_jsonl(path, [row, row], key_field="signal_id",
                                    hash_field="snapshot_payload_sha256")
    assert result == {"appended": 1, "duplicates": 1}


def test_stage_event_digest_is_verified_when_appended(tmp_path: Path):
    event = build_stage_event(
        signal_id="b" * 64, eod_date="2026-11-09", symbol="RELIANCE",
        strategy_version=SHA, stage_name="DELIVERY_30D_AB", status="PASS",
        observed_at_utc="2026-11-10T10:00:00+00:00",
    )
    path = tmp_path / "events.jsonl"
    assert append_immutable_jsonl(path, [event], key_field="event_id",
                                  hash_field="event_id") == {"appended": 1, "duplicates": 0}


def test_snapshot_append_rejects_unapproved_top_level_field_even_with_valid_hash():
    row = snapshot()
    row["private_note"] = "must not persist"
    from signal_shadow_store import _canonical_json, _sha256
    payload = {key: value for key, value in row.items()
               if key not in {"WorkflowRunId", "WorkflowRunAttempt", "CreatedAtUTC", "snapshot_payload_sha256"}}
    row["snapshot_payload_sha256"] = _sha256(_canonical_json(payload))
    with pytest.raises(SignalValidationError, match="schema mismatch"):
        append_immutable_jsonl(Path("unused.jsonl"), [row], key_field="signal_id",
                               hash_field="snapshot_payload_sha256")


def test_stage_event_append_rejects_unapproved_field_even_with_valid_hash():
    from signal_shadow_store import _canonical_json, _sha256
    event = build_stage_event(
        signal_id="b" * 64, eod_date="2026-11-09", symbol="RELIANCE",
        strategy_version=SHA, stage_name="DELIVERY_30D_AB", status="PASS",
        observed_at_utc="2026-11-10T10:00:00+00:00",
    )
    event["account_size"] = 100000
    payload = {key: value for key, value in event.items()
               if key not in {"event_id", "ObservedAtUTC"}}
    event["event_id"] = _sha256(_canonical_json(payload))
    with pytest.raises(SignalValidationError, match="schema mismatch"):
        append_immutable_jsonl(Path("unused-events.jsonl"), [event], key_field="event_id",
                               hash_field="event_id")


@pytest.mark.parametrize("bad_record", [["not", "a", "mapping"], "not-a-mapping"])
def test_jsonl_append_rejects_non_mapping_records(tmp_path: Path, bad_record):
    with pytest.raises(SignalValidationError, match="must be a mapping"):
        append_immutable_jsonl(tmp_path / "invalid.jsonl", [bad_record],
                               key_field="signal_id", hash_field="snapshot_payload_sha256")
