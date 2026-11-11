import csv

from signal_history_persistence import (
    OUTCOME_COLUMNS, SCHEMA_VERSION, SIGNAL_COLUMNS,
    persist_history, restore_history,
)


def _write(path, columns, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _signal(day, symbol, status="WATCH"):
    return {column: "" for column in SIGNAL_COLUMNS} | {
        "EODDate": day, "TckrSymb": symbol, "EODWatchlistStatus": status,
        "ClsPric": "100",
    }


def _outcome(day, symbol, horizon="5"):
    return {column: "" for column in OUTCOME_COLUMNS} | {
        "EODDate": day, "TckrSymb": symbol, "HorizonSessions": horizon,
        "OutcomeStatus": "COMPLETE", "EntryReferenceType": "SIGNAL_EOD_CLOSE",
        "FeesSlippageAssumption": "NOT_CONFIGURED",
    }


def test_restore_initializes_schema_and_persist_appends_only_new_signal_rows(tmp_path):
    history = tmp_path / "data/signal_history/signal_log.csv"
    schema = tmp_path / "data/signal_history/schema_version.txt"
    output = tmp_path / "outputs"
    assert restore_history(history, tmp_path / "data/signal_history/signal_outcomes.csv", schema, output)
    assert schema.read_text().strip() == SCHEMA_VERSION
    source = output / "signal_log.csv"
    _write(source, SIGNAL_COLUMNS, [_signal("2026-11-10", "ABC")])
    result = persist_history(source, output / "signal_outcomes.csv", history, tmp_path / "data/signal_history/signal_outcomes.csv", schema)
    assert result["signals_appended"] == 1
    saved = list(csv.DictReader(history.open(newline="", encoding="utf-8")))
    assert len(saved) == 1 and saved[0]["Result5D"] == ""


def test_existing_signal_rows_are_immutable_even_when_run_copy_has_outcomes(tmp_path):
    history = tmp_path / "history.csv"
    schema = tmp_path / "schema.txt"
    schema.write_text(SCHEMA_VERSION)
    original = _signal("2026-11-10", "ABC")
    _write(history, SIGNAL_COLUMNS, [original])
    source = tmp_path / "run.csv"
    enriched = dict(original, Result5D="2.5", MFE="4.0", MAE="-1.0")
    new = _signal("2026-11-11", "XYZ")
    _write(source, SIGNAL_COLUMNS, [enriched, new])
    result = persist_history(source, tmp_path / "outcomes.csv", history, tmp_path / "outcomes-history.csv", schema)
    assert result["signals_appended"] == 1
    saved = list(csv.DictReader(history.open(newline="", encoding="utf-8")))
    assert saved[0]["Result5D"] == ""
    assert saved[1]["TckrSymb"] == "XYZ"


def test_changed_existing_signal_fields_fail_closed(tmp_path):
    history = tmp_path / "history.csv"
    schema = tmp_path / "schema.txt"
    schema.write_text(SCHEMA_VERSION)
    _write(history, SIGNAL_COLUMNS, [_signal("2026-11-10", "ABC")])
    source = tmp_path / "run.csv"
    _write(source, SIGNAL_COLUMNS, [_signal("2026-11-10", "ABC", "SKIP")])
    result = persist_history(source, tmp_path / "outcomes.csv", history, tmp_path / "outcomes-history.csv", schema)
    assert result["signals_appended"] == 0
    saved = list(csv.DictReader(history.open(newline="", encoding="utf-8")))
    assert saved[0]["EODWatchlistStatus"] == "WATCH"


def test_outcomes_append_once_and_reject_conflicting_rewrite(tmp_path):
    history = tmp_path / "history.csv"
    schema = tmp_path / "schema.txt"
    schema.write_text(SCHEMA_VERSION)
    signal = tmp_path / "signal.csv"
    _write(signal, SIGNAL_COLUMNS, [_signal("2026-11-10", "ABC")])
    outcome_source = tmp_path / "outcomes.csv"
    _write(outcome_source, OUTCOME_COLUMNS, [_outcome("2026-11-10", "ABC")])
    result = persist_history(signal, outcome_source, history, tmp_path / "outcomes-history.csv", schema)
    assert result["outcomes_appended"] == 1
    assert persist_history(signal, outcome_source, history, tmp_path / "outcomes-history.csv", schema)["outcomes_appended"] == 0
    changed = _outcome("2026-11-10", "ABC")
    changed["CloseReturnPct"] = "9.9"
    _write(outcome_source, OUTCOME_COLUMNS, [changed])
    result = persist_history(signal, outcome_source, history, tmp_path / "outcomes-history.csv", schema)
    assert result["outcomes_appended"] == 0
    saved = list(csv.DictReader((tmp_path / "outcomes-history.csv").open(newline="", encoding="utf-8")))
    assert saved[0]["CloseReturnPct"] == ""

def test_durable_signal_byte_limit_is_checked_before_append(tmp_path):
    history = tmp_path / "history.csv"
    schema = tmp_path / "schema.txt"
    schema.write_text(SCHEMA_VERSION)
    old = _signal("2026-11-10", "ABC")
    # A large legacy outcome field must not let the durable file exceed its cap
    # merely because the restored run copy has that outcome field blank.
    old["Result5D"] = "9" * 500
    _write(history, SIGNAL_COLUMNS, [old])

    source = tmp_path / "run.csv"
    _write(source, SIGNAL_COLUMNS, [dict(old, Result5D=""), _signal("2026-11-11", "XYZ")])
    limit = source.stat().st_size + 10
    try:
        persist_history(
            source, tmp_path / "outcomes.csv", history,
            tmp_path / "outcomes-history.csv", schema,
            max_signal_bytes=limit,
        )
    except ValueError as exc:
        assert "size limit" in str(exc)
    else:
        raise AssertionError("durable signal byte limit was not enforced")
    saved = list(csv.DictReader(history.open(newline="", encoding="utf-8")))
    assert len(saved) == 1
    assert saved[0]["TckrSymb"] == "ABC"
