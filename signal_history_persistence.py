"""Safe repository persistence for append-only NSE V8 signal/outcome history."""
from __future__ import annotations

import argparse
import csv
import io
from pathlib import Path
import shutil

SCHEMA_VERSION = "1.0"
SIGNAL_COLUMNS = [
    "EODDate", "TckrSymb", "EODWatchlistStatus", "DeliveryCategory",
    "LiquidityTier", "RVOL", "SetupType", "TrendClassification",
    "RelativeStrengthNifty", "V8Score", "EntryZoneLow", "EntryZoneHigh",
    "StopLoss", "Target/RiskReward", "StopDistancePct",
    "SectorStrengthStatus", "MarketRegimeStatus", "ClsPric",
    "Result5D", "Result10D", "Result20D", "MFE", "MAE",
]
OUTCOME_COLUMNS = [
    "EODDate", "TckrSymb", "HorizonSessions", "OutcomeStatus",
    "HorizonEndDate", "EntryReference", "EntryReferenceType",
    "CloseReturnPct", "MFE_Pct", "MAE_Pct", "ObservedSessionCount",
    "PriceSource", "FeesSlippageAssumption",
]
OUTCOME_VALUE_COLUMNS = {"Result5D", "Result10D", "Result20D", "MFE", "MAE"}


def _read_csv(path: Path, expected: list[str]) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != expected:
            raise ValueError(f"schema mismatch in {path}")
        return list(reader)


def _assert_unique(rows, key_fields, label):
    seen = set()
    for row in rows:
        key = tuple(row.get(field, "") for field in key_fields)
        if not all(key) or key in seen:
            raise ValueError(f"{label}: duplicate or empty key {key}")
        seen.add(key)
    return seen


def _serialized_csv_bytes(rows, columns, *, include_header=False) -> int:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=columns)
    if include_header:
        writer.writeheader()
    writer.writerows(rows)
    return len(buffer.getvalue().encode("utf-8"))


def restore_history(
    history_path="data/signal_history/signal_log.csv",
    outcomes_path="data/signal_history/signal_outcomes.csv",
    schema_path="data/signal_history/schema_version.txt",
    output_dir="outputs",
) -> bool:
    history = Path(history_path)
    outcomes = Path(outcomes_path)
    schema = Path(schema_path)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    if history.exists():
        if not schema.exists() or schema.read_text(encoding="utf-8").strip() != SCHEMA_VERSION:
            print("[SIGNAL HISTORY] WARNING: schema version mismatch; durable history not restored.")
            return False
        try:
            rows = _read_csv(history, SIGNAL_COLUMNS)
            _assert_unique(rows, ("EODDate", "TckrSymb"), "signal history")
        except Exception as exc:
            print(f"[SIGNAL HISTORY] WARNING: durable signal store invalid; scanner continues without restoring it: {exc}")
            return False
        shutil.copy2(history, output / "signal_log.csv")
        if outcomes.exists():
            try:
                outcome_rows = _read_csv(outcomes, OUTCOME_COLUMNS)
                _assert_unique(outcome_rows, ("EODDate", "TckrSymb", "HorizonSessions"), "signal outcomes")
                shutil.copy2(outcomes, output / "signal_outcomes.csv")
            except Exception as exc:
                print(f"[SIGNAL OUTCOMES] WARNING: durable outcome store not restored; scanner continues: {exc}")
        print(f"[SIGNAL HISTORY] Restored {len(rows)} immutable signal rows.")
    else:
        schema.parent.mkdir(parents=True, exist_ok=True)
        schema.write_text(SCHEMA_VERSION + "\n", encoding="utf-8")
        print("[SIGNAL HISTORY] First run: schema marker initialized; no prior history.")
    return True


def persist_history(
    signal_source="outputs/signal_log.csv",
    outcome_source="outputs/signal_outcomes.csv",
    history_path="data/signal_history/signal_log.csv",
    outcomes_path="data/signal_history/signal_outcomes.csv",
    schema_path="data/signal_history/schema_version.txt",
    max_signal_rows=100000,
    max_signal_bytes=25 * 1024 * 1024,
    max_outcome_rows=300000,
    max_outcome_bytes=50 * 1024 * 1024,
) -> dict[str, int]:
    source = Path(signal_source)
    outcome_src = Path(outcome_source)
    history = Path(history_path)
    outcomes_history = Path(outcomes_path)
    schema = Path(schema_path)
    if not source.exists() or source.stat().st_size == 0:
        print("[SIGNAL HISTORY] WARNING: per-run signal log missing/empty; persistence skipped.")
        return {"signals_appended": 0, "outcomes_appended": 0}
    if not schema.exists() or schema.read_text(encoding="utf-8").strip() != SCHEMA_VERSION:
        print("[SIGNAL HISTORY] WARNING: schema version mismatch; persistence skipped.")
        return {"signals_appended": 0, "outcomes_appended": 0}

    try:
        current = _read_csv(source, SIGNAL_COLUMNS)
        old = _read_csv(history, SIGNAL_COLUMNS)
        _assert_unique(current, ("EODDate", "TckrSymb"), "per-run signal log")
        _assert_unique(old, ("EODDate", "TckrSymb"), "durable signal history")
        old_by_key = {(row["EODDate"], row["TckrSymb"]): row for row in old}
        current_by_key = {(row["EODDate"], row["TckrSymb"]): row for row in current}
        if not set(old_by_key).issubset(current_by_key):
            raise ValueError("per-run signal log is missing previously persisted keys")
        for key, old_row in old_by_key.items():
            new_row = current_by_key[key]
            for column in SIGNAL_COLUMNS:
                if column not in OUTCOME_VALUE_COLUMNS and old_row[column] != new_row[column]:
                    raise ValueError(f"immutable signal field changed for {key}: {column}")
    except Exception as exc:
        print(f"[SIGNAL HISTORY] WARNING: immutable history validation failed; no signal rows appended: {exc}")
        return {"signals_appended": 0, "outcomes_appended": 0}

    additions = []
    for row in current:
        key = (row["EODDate"], row["TckrSymb"])
        if key not in old_by_key:
            record = dict(row)
            for column in OUTCOME_VALUE_COLUMNS:
                record[column] = ""
            additions.append(record)
    signal_append_bytes = _serialized_csv_bytes(
        additions, SIGNAL_COLUMNS, include_header=not history.exists()
    )
    durable_signal_bytes = history.stat().st_size if history.exists() else 0
    if (
        len(old) + len(additions) > max_signal_rows
        or durable_signal_bytes + signal_append_bytes > max_signal_bytes
        or source.stat().st_size > max_signal_bytes
    ):
        raise ValueError("signal history size limit reached; archive policy review required")
    if not history.exists():
        history.parent.mkdir(parents=True, exist_ok=True)
        with history.open("w", newline="", encoding="utf-8") as handle:
            csv.writer(handle).writerow(SIGNAL_COLUMNS)
    if additions:
        with history.open("a", newline="", encoding="utf-8") as handle:
            csv.DictWriter(handle, fieldnames=SIGNAL_COLUMNS).writerows(additions)

    outcomes_appended = 0
    if outcome_src.exists() and outcome_src.stat().st_size:
        try:
            current_outcomes = _read_csv(outcome_src, OUTCOME_COLUMNS)
            old_outcomes = _read_csv(outcomes_history, OUTCOME_COLUMNS)
            _assert_unique(current_outcomes, ("EODDate", "TckrSymb", "HorizonSessions"), "per-run outcomes")
            _assert_unique(old_outcomes, ("EODDate", "TckrSymb", "HorizonSessions"), "durable outcomes")
            old_outcome_map = {
                (row["EODDate"], row["TckrSymb"], row["HorizonSessions"]): row
                for row in old_outcomes
            }
            outcome_additions = []
            for row in current_outcomes:
                key = (row["EODDate"], row["TckrSymb"], row["HorizonSessions"])
                if key in old_outcome_map:
                    if old_outcome_map[key] != row:
                        raise ValueError(f"immutable outcome conflict for {key}")
                else:
                    old_outcome_map[key] = row
                    outcome_additions.append(row)
            outcome_append_bytes = _serialized_csv_bytes(
                outcome_additions, OUTCOME_COLUMNS, include_header=not outcomes_history.exists()
            )
            durable_outcome_bytes = outcomes_history.stat().st_size if outcomes_history.exists() else 0
            if (
                len(old_outcomes) + len(outcome_additions) > max_outcome_rows
                or durable_outcome_bytes + outcome_append_bytes > max_outcome_bytes
                or outcome_src.stat().st_size > max_outcome_bytes
            ):
                raise ValueError("signal outcome history size limit reached; archive policy review required")
            if outcome_additions:
                outcomes_history.parent.mkdir(parents=True, exist_ok=True)
                if not outcomes_history.exists():
                    with outcomes_history.open("w", newline="", encoding="utf-8") as handle:
                        csv.writer(handle).writerow(OUTCOME_COLUMNS)
                with outcomes_history.open("a", newline="", encoding="utf-8") as handle:
                    csv.DictWriter(handle, fieldnames=OUTCOME_COLUMNS).writerows(outcome_additions)
            outcomes_appended = len(outcome_additions)
        except Exception as exc:
            print(f"[SIGNAL OUTCOMES] WARNING: outcome persistence skipped; scanner continues: {exc}")

    print(f"[SIGNAL HISTORY] Appended {len(additions)} new immutable signal rows.")
    print(f"[SIGNAL HISTORY] Appended {outcomes_appended} new immutable outcome rows.")
    return {"signals_appended": len(additions), "outcomes_appended": outcomes_appended}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("restore", "persist"))
    args = parser.parse_args()
    if args.action == "restore":
        restore_history()
    else:
        persist_history()


if __name__ == "__main__":
    main()
