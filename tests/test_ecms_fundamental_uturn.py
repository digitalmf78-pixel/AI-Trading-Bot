import pandas as pd
import pytest

from strategies.ecms.fundamental_uturn import (
    calculate_uturn_targets,
    select_pre_result_peak,
)


def _row(**overrides):
    row = {
        "Symbol": "ABC",
        "Previous_FY": "FY2025",
        "Current_FY": "FY2026",
        "Previous_EPS": 20.0,
        "Current_EPS": 16.0,
        "Previous_EPS_Basis": "DILUTED",
        "Current_EPS_Basis": "DILUTED",
        "Previous_Reporting_Basis": "CONSOLIDATED",
        "Current_Reporting_Basis": "CONSOLIDATED",
        "Previous_EPS_Unit": "INR/SHARE",
        "Current_EPS_Unit": "INR/SHARE",
        "Previous_EPS_Source_URL": "https://www.nseindia.com/filing/previous",
        "Current_EPS_Source_URL": "https://www.nseindia.com/filing/current",
        "Result_Announcement_Source_URL": "https://www.nseindia.com/announcement/result",
        "Result_Announcement_Date": "2026-05-20",
        "Peak_Price": 400.0,
        "Peak_Price_Source_URL": "https://www.nseindia.com/ohlc/peak",
        "Latest_Post_Result_Close": 320.0,
        "Latest_Post_Result_Session": "2026-05-21",
        "Latest_Post_Result_Source_URL": "https://www.nseindia.com/ohlc/latest",
        "EPS_Verified": True,
        "Peak_Price_Verified": True,
        "Corporate_Action_Adjusted": True,
    }
    row.update(overrides)
    return row


def test_example_target_and_equivalent_formula():
    result = calculate_uturn_targets(pd.DataFrame([_row()])).iloc[0]
    assert result["EPS_Drop"] == pytest.approx(4.0)
    assert result["Reference_PE"] == pytest.approx(20.0)
    assert result["Expected_Correction"] == pytest.approx(80.0)
    assert result["U_Turn_Target"] == pytest.approx(320.0)
    assert result["U_Turn_Status"] == "NEAR_UTURN_ZONE"


@pytest.mark.parametrize("current_eps", [20.0, 22.0])
def test_equal_or_higher_eps_has_no_correction(current_eps):
    result = calculate_uturn_targets(pd.DataFrame([_row(Current_EPS=current_eps)])).iloc[0]
    assert result["U_Turn_Status"] == "NO_EPS_DECLINE"
    assert pd.isna(result["U_Turn_Target"])


@pytest.mark.parametrize("previous,current", [(0, 4), (-2, 4), (20, 0), (20, -1)])
def test_non_positive_eps_never_creates_target(previous, current):
    result = calculate_uturn_targets(
        pd.DataFrame([_row(Previous_EPS=previous, Current_EPS=current)])
    ).iloc[0]
    assert result["U_Turn_Status"] == "NOT_COMPARABLE_FOR_THIS_FORMULA"
    assert pd.isna(result["U_Turn_Target"])


def test_basic_eps_is_rejected_without_fallback():
    result = calculate_uturn_targets(pd.DataFrame([_row(Current_EPS_Basis="BASIC")])).iloc[0]
    assert result["U_Turn_Status"] == "WAIT_FOR_DATA"
    assert "Diluted EPS only" in result["U_Turn_Reason"]


def test_reporting_basis_must_match_and_be_explicit():
    result = calculate_uturn_targets(pd.DataFrame([_row(Current_Reporting_Basis="")])).iloc[0]
    assert result["U_Turn_Status"] == "WAIT_FOR_DATA"
    mismatch = calculate_uturn_targets(pd.DataFrame([_row(Current_Reporting_Basis="STANDALONE")])).iloc[0]
    assert mismatch["U_Turn_Status"] == "WAIT_FOR_DATA"


def test_unverified_eps_or_peak_fails_closed():
    for changes in ({"EPS_Verified": False}, {"Peak_Price_Verified": False}):
        result = calculate_uturn_targets(pd.DataFrame([_row(**changes)])).iloc[0]
        assert result["U_Turn_Status"] == "UNVERIFIED"


def test_non_consecutive_financial_years_fail_closed():
    result = calculate_uturn_targets(pd.DataFrame([_row(Current_FY="FY2027")])).iloc[0]
    assert result["U_Turn_Status"] == "WAIT_FOR_DATA"


def test_post_result_close_must_be_after_announcement_date():
    result = calculate_uturn_targets(
        pd.DataFrame([_row(Latest_Post_Result_Session="2026-05-20")])
    ).iloc[0]
    assert result["U_Turn_Status"] == "WAIT_FOR_DATA"


def test_proximity_boundaries_are_inclusive():
    target = 320.0
    low = target * 0.97
    high = target * 1.03
    result = calculate_uturn_targets(pd.DataFrame([
        _row(Symbol="LOW", Latest_Post_Result_Close=low),
        _row(Symbol="HIGH", Latest_Post_Result_Close=high),
    ]))
    assert result["Near_U_Turn_Support"].tolist() == [True, True]


def test_pre_result_peak_uses_last_20_sessions_and_excludes_event_date():
    dates = pd.bdate_range("2026-04-20", periods=22)
    frame = pd.DataFrame({"Date": dates, "High": [100.0] * 22})
    frame.loc[frame["Date"] == dates[-1], "High"] = 999.0
    result = select_pre_result_peak(frame, dates[-1], window_sessions=20)
    assert result["status"] == "READY"
    assert result["Peak_Price"] == pytest.approx(100.0)
    assert result["Peak_Window_Sessions"] == 20
    assert result["Peak_Window_End"] == dates[-2].date().isoformat()


def test_pre_result_peak_requires_full_unique_valid_sessions():
    dates = pd.bdate_range("2026-04-20", periods=20)
    short = pd.DataFrame({"Date": dates[:19], "High": [100.0] * 19})
    assert select_pre_result_peak(short, "2026-05-01")["status"] == "WAIT_FOR_DATA"

    duplicate = pd.concat([short, short.iloc[[0]]], ignore_index=True)
    assert select_pre_result_peak(duplicate, "2026-05-01")["status"] == "WAIT_FOR_DATA"

    invalid = pd.DataFrame({"Date": dates, "High": [100.0] * 19 + [None]})
    assert select_pre_result_peak(invalid, "2026-05-01")["status"] == "WAIT_FOR_DATA"


def test_invalid_tolerance_rejected():
    with pytest.raises(ValueError):
        calculate_uturn_targets(pd.DataFrame([_row()]), tolerance_pct=100)
