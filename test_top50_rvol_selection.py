"""Regression tests for the current uncapped RVOL > 1.5 selection rule."""
import os

import pandas as pd

import volume_gainer as scanner


def test_select_rvol_above_threshold_keeps_all_qualifying_rows_without_top50_cap(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    frame = pd.DataFrame({
        "TckrSymb": [f"S{i:03d}" for i in range(75)],
        "RVOL": [float(i + 1) / 10 for i in range(75)],
        "RVOLStatus": ["PASS"] * 75,
    })

    selected = scanner.select_rvol_above_threshold(frame, "2026-10-22", minimum_rvol=1.5)

    # RVOL strictly greater than 1.5: values 1.6 through 7.5 => 60 rows.
    assert len(selected) == 60
    assert selected.iloc[0]["RVOL"] == 7.5
    assert selected.iloc[-1]["RVOL"] == 1.6
    assert selected["RVOLRank"].tolist() == list(range(1, 61))
    assert (selected["RVOLThresholdStatus"] == "PASS_RVOL_GT_1_5").all()
    assert os.path.exists("outputs/v8_rvol_gt_1_5_audit.csv")
    assert os.path.exists("outputs/v8_rvol_gt_1_5_candidates.csv")


def test_rvol_boundary_and_wait_for_data_are_not_selected(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    frame = pd.DataFrame({
        "TckrSymb": ["ABOVE", "BOUNDARY", "BELOW", "WAIT", "MISSING"],
        "RVOL": [1.5001, 1.5, 1.49, 4.0, None],
        "RVOLStatus": ["PASS", "PASS", "PASS", "WAIT_FOR_DATA", "PASS"],
    })

    selected = scanner.select_rvol_above_threshold(frame, "2026-10-22", minimum_rvol=1.5)

    assert selected["TckrSymb"].tolist() == ["ABOVE"]
