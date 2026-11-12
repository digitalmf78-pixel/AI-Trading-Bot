import json

import pandas as pd

from signal_shadow_run import build_mainboard_signal_shadow


def test_full_mainboard_shadow_is_left_joined_and_does_not_mutate_inputs(tmp_path):
    mainboard = pd.DataFrame([
        {"TckrSymb": "ABC", "SctySrs": "EQ", "ClsPric": 100.0},
        {"TckrSymb": "XYZ", "SctySrs": "EQ", "ClsPric": 50.0},
    ])
    delivery = pd.DataFrame([{
        "TckrSymb": "ABC", "SctySrs": "EQ",
        "DeliveryCategoryAStatus": "PASS_ROLLING_5D_AVG_GE_60_AT_LEAST_5",
        "DeliveryCategoryBStatus": "FILTERED_OUT_DAILY_DELIVERY_LT_5",
        "DeliveryFilterStatus": "PASS_A_OR_B",
    }])
    original = mainboard.copy(deep=True)
    manifest = build_mainboard_signal_shadow(
        mainboard,
        reports={"delivery": delivery, "technical": pd.DataFrame()},
        eod_date="2026-11-11",
        strategy_version="a" * 40,
        output_dir=tmp_path,
    )
    assert manifest["MainboardCohortRows"] == 2
    assert manifest["SnapshotsAppended"] == 2
    pd.testing.assert_frame_equal(mainboard, original)
    cohort = pd.read_csv(tmp_path / "full_mainboard_cohort.csv")
    assert len(cohort) == 2
    assert cohort.loc[cohort.TckrSymb == "XYZ", "delivery__CoverageStatus"].iloc[0] == "NOT_EVALUATED"
    records = [json.loads(line) for line in (tmp_path / "snapshots.jsonl").read_text().splitlines()]
    assert len(records) == 2
    assert all(record["RunMode"] == "EOD" for record in records)
    assert all(record["signal_fields"].get("Close") in (100.0, 50.0) for record in records)


def test_exact_snapshot_retry_is_idempotent(tmp_path):
    mainboard = pd.DataFrame([{"TckrSymb": "ABC", "SctySrs": "EQ", "ClsPric": 100.0}])
    kwargs = dict(
        mainboard_candidates=mainboard, reports={}, eod_date="2026-11-11",
        strategy_version="b" * 40, output_dir=tmp_path,
        workflow_run_id="123", workflow_run_attempt="1",
    )
    first = build_mainboard_signal_shadow(**kwargs)
    second = build_mainboard_signal_shadow(**kwargs)
    assert first["SnapshotsAppended"] == 1
    assert second["SnapshotsAppended"] == 0
    assert second["ExactDuplicates"] == 1
