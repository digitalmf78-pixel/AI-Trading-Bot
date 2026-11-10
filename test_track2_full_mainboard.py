from datetime import date
import json

import pandas as pd

import track2_full_mainboard as track2


def _candidates():
    return pd.DataFrame([
        {"TckrSymb": "AAA", "SctySrs": "EQ", "MainBoardStatus": "PASS_MAIN_BOARD",
         "BoardClassification": "MAIN_BOARD", "DeliveryFilterStatus": "FILTERED_OUT_A_AND_B"},
        {"TckrSymb": "BBB", "SctySrs": "EQ", "MainBoardStatus": "PASS_MAIN_BOARD",
         "BoardClassification": "MAIN_BOARD", "DeliveryFilterStatus": "PASS_A_OR_B"},
        {"TckrSymb": "CCC", "SctySrs": "BE", "MainBoardStatus": "PASS_MAIN_BOARD",
         "BoardClassification": "MAIN_BOARD", "DeliveryFilterStatus": "WAIT_FOR_DATA"},
    ])


def _patch_observers(monkeypatch, calls=None):
    calls = calls if calls is not None else {}

    def delivery(candidates, asof, sessions, output_path=None):
        calls["delivery"] = (set(candidates.TckrSymb), str(output_path))
        result = candidates[["TckrSymb"]].copy()
        result["DeliveryQuantityStatus"] = "COMPLETE_5_10_20D"
        result["DeliveryQty5DTotal"] = 100
        return result, result

    def accumulation(candidates, historical, sessions, asof, output_path=None):
        calls["accumulation"] = (set(candidates.TckrSymb), str(output_path))
        result = candidates[["TckrSymb"]].copy()
        result["EvidenceStatus"] = "OBSERVATIONS_AVAILABLE"
        result["PriceRange20DStatus"] = "OBSERVATION_AVAILABLE"
        return result

    def vcp(candidates, historical, asof, output_path=None):
        calls["vcp"] = (set(candidates.TckrSymb), str(output_path))
        result = candidates[["TckrSymb"]].copy()
        result["VCPObservationStatus"] = "COMPLETE"
        result["VCPStatus"] = "NOT_CLASSIFIED"
        return result

    monkeypatch.setattr(track2, "build_delivery_quantity_report", delivery)
    monkeypatch.setattr(track2, "build_potential_accumulation_report", accumulation)
    monkeypatch.setattr(track2, "build_vcp_observation_report", vcp)
    return calls


def test_full_mainboard_cohort_is_observed_not_only_delivery_ab_union(tmp_path, monkeypatch):
    calls = _patch_observers(monkeypatch)
    report, manifest = track2.build_track2_full_mainboard_report(
        _candidates(), [], [], "2026-11-09", output_dir=tmp_path
    )
    expected = {"AAA", "BBB", "CCC"}
    assert len(report) == 3
    assert set(report.TckrSymb) == expected
    assert all(calls[name][0] == expected for name in ("delivery", "accumulation", "vcp"))
    assert all("track2_full_mainboard" in calls[name][1] or "track2_" in calls[name][1]
               for name in calls)
    assert report["Track2CohortStatus"].eq("PASS_MAIN_BOARD_INPUT").all()
    assert report["Track2DeliveryQuantityObserverStatus"].eq("COMPLETE_5_10_20D").all()
    assert report["Track2PotentialAccumulationObserverStatus"].eq("OBSERVATIONS_AVAILABLE").all()
    assert report["Track2VCPObserverStatus"].eq("COMPLETE").all()
    assert report["ResearchPatternStatus"].eq("NOT_CLASSIFIED_PENDING_APPROVED_RULES").all()
    assert report["ResearchPatternRequested"].eq("BOTH").all()
    assert manifest["eligible_unique_mainboard_symbols"] == 3
    assert manifest["output_rows"] == 3
    assert (tmp_path / "v8_track2_full_mainboard_cohort_20261109.csv").exists()
    assert (tmp_path / "v8_track2_coverage_manifest_20261109.json").exists()


def test_duplicate_cohort_symbol_is_retained_once_and_fails_closed(tmp_path, monkeypatch):
    calls = _patch_observers(monkeypatch)
    source = pd.concat([_candidates(), _candidates().iloc[[0]]], ignore_index=True)
    report, manifest = track2.build_track2_full_mainboard_report(
        source, [], [], "2026-11-09", output_dir=tmp_path
    )
    assert len(report) == 3
    duplicate = report.loc[report.TckrSymb.eq("AAA")].iloc[0]
    assert duplicate.Track2CohortStatus == "WAIT_FOR_DATA"
    assert duplicate.Track2CohortReason == "DUPLICATE_COHORT_SYMBOL"
    assert calls["delivery"][0] == {"BBB", "CCC"}
    assert manifest["duplicate_symbol_count"] == 1
    assert manifest["cohort_status"] == "PARTIAL_INPUT_IDENTITY"


def test_observer_failure_isolated_and_never_drops_full_cohort(tmp_path, monkeypatch):
    calls = _patch_observers(monkeypatch)

    def fail_accumulation(*args, **kwargs):
        raise RuntimeError("synthetic accumulation failure")

    monkeypatch.setattr(track2, "build_potential_accumulation_report", fail_accumulation)
    report, manifest = track2.build_track2_full_mainboard_report(
        _candidates(), [], [], "2026-11-09", output_dir=tmp_path
    )
    assert set(report.TckrSymb) == {"AAA", "BBB", "CCC"}
    assert report["Track2DeliveryQuantityObserverStatus"].eq("COMPLETE_5_10_20D").all()
    assert report["Track2PotentialAccumulationObserverStatus"].eq("WAIT_FOR_DATA").all()
    assert report["Track2VCPObserverStatus"].eq("COMPLETE").all()
    assert "synthetic accumulation failure" in manifest["observers"]["potential_accumulation"]["error"]


def test_unverified_board_rows_are_retained_but_not_sent_to_observers(tmp_path, monkeypatch):
    calls = _patch_observers(monkeypatch)
    source = _candidates()
    source.loc[source.TckrSymb.eq("BBB"), "MainBoardStatus"] = "EXCLUDED_SME"
    report, manifest = track2.build_track2_full_mainboard_report(
        source, [], [], "2026-11-09", output_dir=tmp_path
    )
    assert len(report) == 3
    rejected = report.loc[report.TckrSymb.eq("BBB")].iloc[0]
    assert rejected.Track2CohortStatus == "WAIT_FOR_DATA"
    assert rejected.Track2CohortReason == "INPUT_NOT_VERIFIED_AS_MAIN_BOARD"
    assert calls["delivery"][0] == {"AAA", "CCC"}
    assert manifest["output_rows"] == 3


def test_invalid_symbol_rows_remain_visible_as_wait_for_data(tmp_path, monkeypatch):
    _patch_observers(monkeypatch)
    source = _candidates()
    source.loc[0, "TckrSymb"] = None
    report, manifest = track2.build_track2_full_mainboard_report(
        source, [], [], "2026-11-09", output_dir=tmp_path
    )
    invalid = report.loc[report.TckrSymb.eq("")].iloc[0]
    assert invalid.Track2CohortStatus == "WAIT_FOR_DATA"
    assert invalid.Track2CohortReason == "INVALID_SYMBOL_IDENTITY"
    assert invalid.ResearchPatternStatus == "WAIT_FOR_DATA"
    assert manifest["invalid_symbol_row_count"] == 1
    assert manifest["output_rows"] == 3


def test_pattern_request_rejects_unapproved_arbitrary_category(tmp_path, monkeypatch):
    _patch_observers(monkeypatch)
    try:
        track2.build_track2_full_mainboard_report(
            _candidates(), [], [], "2026-11-09", output_dir=tmp_path,
            research_pattern_requested="BUY_NOW",
        )
    except ValueError as exc:
        assert "research_pattern_requested" in str(exc)
    else:
        raise AssertionError("Unrecognized research pattern request must be rejected")


def test_empty_cohort_writes_empty_report_and_manifest(tmp_path):
    report, manifest = track2.build_track2_full_mainboard_report(
        pd.DataFrame(), [], [], "2026-11-09", output_dir=tmp_path
    )
    assert report.empty
    assert manifest["cohort_status"] == "EMPTY_INPUT"
    payload = json.loads((tmp_path / "v8_track2_coverage_manifest_20261109.json").read_text())
    assert payload["output_rows"] == 0


def test_asof_date_is_required_and_validated(tmp_path):
    try:
        track2.build_track2_full_mainboard_report(
            _candidates(), [], [], "not-a-date", output_dir=tmp_path
        )
    except ValueError as exc:
        assert "Invalid as-of date" in str(exc)
    else:
        raise AssertionError("Invalid as-of date must fail")


def test_synthetic_2588_symbol_mainboard_cohort_has_exact_coverage(tmp_path, monkeypatch):
    calls = _patch_observers(monkeypatch)
    source = pd.DataFrame({
        "TckrSymb": [f"SYM{i:04d}" for i in range(2588)],
        "SctySrs": ["EQ"] * 2385 + ["BE"] * 203,
        "MainBoardStatus": ["PASS_MAIN_BOARD"] * 2588,
        "BoardClassification": ["MAIN_BOARD"] * 2588,
        "DeliveryFilterStatus": (
            ["FILTERED_OUT_A_AND_B"] * 1830
            + ["PASS_A_ONLY"] * 656
            + ["PASS_A_AND_B"] * 102
        ),
    })
    original = source.copy(deep=True)

    report, manifest = track2.build_track2_full_mainboard_report(
        source, [], [], "2026-11-09", output_dir=tmp_path
    )

    expected = {f"SYM{i:04d}" for i in range(2588)}
    assert len(report) == 2588
    assert report["TckrSymb"].nunique() == 2588
    assert set(report["TckrSymb"]) == expected
    assert report["Track2CohortStatus"].eq("PASS_MAIN_BOARD_INPUT").all()
    assert report["Track2DeliveryQuantityObserverStatus"].eq("COMPLETE_5_10_20D").all()
    assert report["Track2PotentialAccumulationObserverStatus"].eq("OBSERVATIONS_AVAILABLE").all()
    assert report["Track2VCPObserverStatus"].eq("COMPLETE").all()
    assert all(len(calls[name][0]) == 2588 for name in ("delivery", "accumulation", "vcp"))
    assert manifest["expected_input_rows"] == 2588
    assert manifest["eligible_unique_mainboard_symbols"] == 2588
    assert manifest["output_rows"] == 2588
    assert manifest["cohort_status"] == "COMPLETE"
    saved = pd.read_csv(tmp_path / "v8_track2_full_mainboard_cohort_20261109.csv")
    assert len(saved) == 2588
    assert saved["TckrSymb"].nunique() == 2588
    pd.testing.assert_frame_equal(source, original)
