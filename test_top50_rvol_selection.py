import os
import pandas as pd
import volume_gainer as scanner


def test_select_top50_by_rvol_returns_highest_fifty_and_ranks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    frame = pd.DataFrame({
        "TckrSymb": [f"S{i:03d}" for i in range(60)],
        "RVOL": [float(i + 1) for i in range(60)],
        "RVOLStatus": ["PASS"] * 60,
    })
    selected = scanner.select_top50_by_rvol(frame, "2026-10-22")
    assert len(selected) == 50
    assert selected.iloc[0]["RVOL"] == 60.0
    assert selected.iloc[-1]["RVOL"] == 11.0
    assert selected["PrimaryCandidateRank"].tolist() == list(range(1, 51))
    assert os.path.exists("outputs/v8_primary_shortlist_top50.csv")


def test_rvol_wait_for_data_is_not_ranked(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    frame = pd.DataFrame({
        "TckrSymb": ["A", "B", "C"],
        "RVOL": [5.0, 4.0, 3.0],
        "RVOLStatus": ["PASS", "WAIT_FOR_DATA", "PASS"],
    })
    selected = scanner.select_top50_by_rvol(frame, "2026-10-22")
    assert selected["TckrSymb"].tolist() == ["A", "C"]
