"""Append-only, observational NSE V8 signal snapshot primitives.

This module is deliberately not wired into the production scanner or workflow.
Callers must supply an explicitly curated, already-redacted field mapping.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "1.0"
SIGNAL_TYPE = "EOD_CANDIDATE"
EXCHANGE_TIMEZONE = "Asia/Kolkata"

SAFE_SIGNAL_FIELDS = {
    "Close", "Open", "High", "Low", "Volume", "TtlTrfVal", "SctySrs",
    "RVOL", "RVOLBand", "RVOLThresholdStatus",
    "DeliverySessions", "DeliveryExpectedSessions30D", "DeliveryCoveragePct",
    "DeliveryDailyPassCount", "AvgDelivery30D", "LatestDeliveryPct",
    "DeliveryCategoryAStatus", "DeliveryCategoryBStatus", "DeliveryFilterStatus",
    "LiquiditySessions", "AvgDailyTradedValue20D", "LiquidityStatus",
    "LiquidityFilterStatus", "LiquidityTier",
    "FundamentalStatus", "FundamentalReason",
    "CoreTechnicalScreenStatus", "SetupType", "RelativeStrengthNifty",
    "EntryZoneLow", "EntryZoneHigh", "EntryPricePlan", "StopLossPlan",
    "TargetPricePlan", "TargetSource", "RiskReward", "RiskRewardStatus",
    "EODWatchlistStatus", "EODWatchlistReason",
}
FORBIDDEN_KEY_PARTS = (
    "token", "password", "secret", "api_key", "apikey", "credential",
    "positionqty", "riskbudget", "proposedexposure", "accountsize",
)


class SignalStoreError(RuntimeError):
    """Base exception for invalid or conflicting signal-store operations."""


class SignalConflictError(SignalStoreError):
    """A signal key already exists with a different immutable payload."""


class SignalValidationError(SignalStoreError):
    """A record does not satisfy the minimal signal-store contract."""


def _iso_date(value: str | date) -> str:
    # datetime subclasses date; accepting it would silently serialize a timestamp
    # as EODDate and make the same logical session acquire a different identity.
    if isinstance(value, datetime):
        raise SignalValidationError("EOD date must be a date, not a datetime")
    try:
        parsed = value if isinstance(value, date) else date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise SignalValidationError(f"Invalid EOD date: {value!r}") from exc
    return parsed.isoformat()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _reject_sensitive_keys(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
            if any(part in normalized for part in FORBIDDEN_KEY_PARTS):
                raise SignalValidationError(f"Forbidden sensitive field at {path}.{key}")
            _reject_sensitive_keys(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _reject_sensitive_keys(child, f"{path}[{index}]")


def _require_text(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise SignalValidationError(f"{label} is required")
    return text


def _verified_record_digest(record: Mapping[str, Any], hash_field: str) -> str:
    """Recompute supported immutable digests; never trust a caller-supplied hash."""
    if hash_field == "snapshot_payload_sha256":
        excluded = {"WorkflowRunId", "WorkflowRunAttempt", "CreatedAtUTC", hash_field}
    elif hash_field == "event_id":
        excluded = {"event_id", "ObservedAtUTC"}
    else:
        raise SignalValidationError(f"Unsupported immutable hash field: {hash_field}")
    if hash_field not in record:
        raise SignalValidationError(f"Record requires {hash_field}")
    payload = {key: value for key, value in record.items() if key not in excluded}
    try:
        return _sha256(_canonical_json(payload))
    except (TypeError, ValueError) as exc:
        raise SignalValidationError(f"Record is not canonical JSON: {exc}") from exc


def _validate_record_schema(record: Mapping[str, Any], hash_field: str) -> None:
    """Reject unexpected persisted fields, even if a caller recomputes a valid hash."""
    if not isinstance(record, Mapping):
        raise SignalValidationError("Persisted signal record must be a mapping")
    if hash_field == "snapshot_payload_sha256":
        allowed = {
            "schema_version", "signal_id", "EODDate", "Symbol", "SignalType",
            "StrategyVersion", "RunMode", "ExchangeTimezone", "signal_fields",
            "source_reports", "WorkflowRunId", "WorkflowRunAttempt",
            "CreatedAtUTC", "snapshot_payload_sha256",
        }
        if set(record) != allowed:
            unexpected = sorted(map(str, set(record) - allowed))
            missing = sorted(allowed - set(record))
            raise SignalValidationError(
                f"Snapshot record schema mismatch; unexpected={unexpected}, missing={missing}"
            )
        fields = record.get("signal_fields")
        if not isinstance(fields, Mapping):
            raise SignalValidationError("Snapshot signal_fields must be a mapping")
        if any(not isinstance(key, str) for key in fields):
            raise SignalValidationError("Persisted signal_fields keys must be strings")
        unknown = sorted(set(fields) - SAFE_SIGNAL_FIELDS)
        if unknown:
            raise SignalValidationError(f"Unapproved persisted signal fields: {', '.join(unknown)}")
        reports = record.get("source_reports")
        if not isinstance(reports, list) or any(not isinstance(item, str) for item in reports):
            raise SignalValidationError("Snapshot source_reports must be a list of strings")
        _reject_sensitive_keys(record)
    elif hash_field == "event_id":
        allowed = {
            "event_id", "signal_id", "EODDate", "Symbol", "StageName", "Status",
            "ReasonCode", "ReasonText", "StrategyVersion", "SourceReport",
            "SourceRowHash", "ObservedAtUTC",
        }
        if set(record) != allowed:
            unexpected = sorted(map(str, set(record) - allowed))
            missing = sorted(allowed - set(record))
            raise SignalValidationError(
                f"Stage-event record schema mismatch; unexpected={unexpected}, missing={missing}"
            )
        _reject_sensitive_keys(record)
    else:
        raise SignalValidationError(f"Unsupported immutable hash field: {hash_field}")


def build_signal_snapshot(
    *,
    eod_date: str | date,
    symbol: str,
    strategy_version: str,
    signal_fields: Mapping[str, Any],
    workflow_run_id: str = "",
    workflow_run_attempt: str = "",
    run_mode: str = "EOD",
    created_at_utc: str | None = None,
    source_reports: Iterable[str] = (),
) -> dict[str, Any]:
    """Build one deterministic-identity snapshot from a curated field mapping."""
    day = _iso_date(eod_date)
    ticker = _require_text(symbol, "symbol").upper()
    version = _require_text(strategy_version, "strategy_version")
    mode = _require_text(run_mode, "run_mode").upper()
    if mode != "EOD":
        raise SignalValidationError("Only EOD runs may create signal snapshots")
    if not isinstance(signal_fields, Mapping):
        raise SignalValidationError("signal_fields must be a mapping")
    if any(not isinstance(key, str) for key in signal_fields):
        raise SignalValidationError("signal_fields keys must be strings")
    unknown = sorted(set(signal_fields) - SAFE_SIGNAL_FIELDS)
    if unknown:
        raise SignalValidationError(f"Unapproved signal fields: {', '.join(unknown)}")
    if isinstance(source_reports, (str, bytes)):
        raise SignalValidationError("source_reports must be an iterable of report names, not a string")
    _reject_sensitive_keys(signal_fields)

    safe_fields = dict(signal_fields)
    try:
        _canonical_json(safe_fields)
    except (TypeError, ValueError) as exc:
        raise SignalValidationError(f"Signal fields are not canonical JSON values: {exc}") from exc

    identity = "|".join((day, ticker, version, SIGNAL_TYPE))
    signal_id = _sha256(identity)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "signal_id": signal_id,
        "EODDate": day,
        "Symbol": ticker,
        "SignalType": SIGNAL_TYPE,
        "StrategyVersion": version,
        "RunMode": mode,
        "ExchangeTimezone": EXCHANGE_TIMEZONE,
        "signal_fields": safe_fields,
        "source_reports": sorted({str(item) for item in source_reports}),
    }
    payload_hash = _sha256(_canonical_json(payload))
    timestamp = created_at_utc or datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        parsed_timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise SignalValidationError("created_at_utc must be an ISO-8601 timestamp") from exc
    if parsed_timestamp.tzinfo is None:
        raise SignalValidationError("created_at_utc must include a timezone")
    return {
        **payload,
        "WorkflowRunId": str(workflow_run_id),
        "WorkflowRunAttempt": str(workflow_run_attempt),
        "CreatedAtUTC": timestamp,
        "snapshot_payload_sha256": payload_hash,
    }


def build_stage_event(
    *,
    signal_id: str,
    eod_date: str | date,
    symbol: str,
    strategy_version: str,
    stage_name: str,
    status: str,
    reason_code: str = "",
    reason_text: str = "",
    source_report: str = "",
    source_row_hash: str = "",
    observed_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic stage event; source statuses are preserved verbatim."""
    day = _iso_date(eod_date)
    fields = {
        "signal_id": _require_text(signal_id, "signal_id"),
        "EODDate": day,
        "Symbol": _require_text(symbol, "symbol").upper(),
        "StageName": _require_text(stage_name, "stage_name"),
        "Status": _require_text(status, "status"),
        "ReasonCode": str(reason_code or ""),
        "ReasonText": str(reason_text or ""),
        "StrategyVersion": _require_text(strategy_version, "strategy_version"),
        "SourceReport": str(source_report or ""),
        "SourceRowHash": str(source_row_hash or ""),
    }
    _reject_sensitive_keys(fields)
    event_id = _sha256(_canonical_json(fields))
    timestamp = observed_at_utc or datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise SignalValidationError("observed_at_utc must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise SignalValidationError("observed_at_utc must include a timezone")
    return {"event_id": event_id, **fields, "ObservedAtUTC": timestamp}


def append_immutable_jsonl(path: str | Path, records: Iterable[Mapping[str, Any]], *,
                           key_field: str, hash_field: str) -> dict[str, int]:
    """Append records; verify hashes, make exact retries no-ops, reject conflicts.

    Supports snapshot_payload_sha256 snapshots and event_id stage events.
    Existing records are never rewritten. Workflow branch concurrency must
    serialize repository writes; this function does not provide file locking.
    """
    target = Path(path)
    pending = list(records)
    if not pending:
        return {"appended": 0, "duplicates": 0}
    existing: dict[str, str] = {}
    if target.exists():
        with target.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                    _validate_record_schema(row, hash_field)
                    key, digest = str(row[key_field]), str(row[hash_field])
                    actual_digest = _verified_record_digest(row, hash_field)
                except (json.JSONDecodeError, KeyError, TypeError, SignalValidationError) as exc:
                    raise SignalStoreError(f"Invalid or tampered JSONL record at {target}:{line_number}: {exc}") from exc
                if digest != actual_digest:
                    raise SignalStoreError(f"Stored record hash mismatch at {target}:{line_number}")
                if key in existing and existing[key] != digest:
                    raise SignalStoreError(f"Existing partition contains conflicting key {key}")
                existing[key] = digest

    seen_batch: dict[str, str] = {}
    append_rows: list[str] = []
    duplicates = 0
    for record in pending:
        _validate_record_schema(record, hash_field)
        if key_field not in record or hash_field not in record:
            raise SignalValidationError(f"Record requires {key_field} and {hash_field}")
        key, digest = str(record[key_field]), str(record[hash_field])
        actual_digest = _verified_record_digest(record, hash_field)
        if digest != actual_digest:
            raise SignalValidationError(f"Record hash mismatch for key {key}")
        if key in seen_batch:
            if seen_batch[key] != digest:
                raise SignalConflictError(f"Conflicting duplicate key in input batch: {key}")
            duplicates += 1
            continue
        seen_batch[key] = digest
        if key in existing:
            if existing[key] != digest:
                raise SignalConflictError(f"Immutable record conflict for key {key}; existing record preserved")
            duplicates += 1
            continue
        append_rows.append(_canonical_json(dict(record)))
        existing[key] = digest

    if append_rows:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8", newline="\n") as stream:
            for row in append_rows:
                stream.write(row + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    return {"appended": len(append_rows), "duplicates": duplicates}
