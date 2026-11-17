"""Research-only annual-EPS U-Turn valuation reset calculator.

This module is deliberately independent of ECMS scan decisions and workflows.
It does not fetch data, create trading signals, or claim that a calculated zone
is support. Inputs must already be reconciled to official filings and exchange
OHLC data by the caller.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Iterable

import pandas as pd

CALCULATION_VERSION = "ecms-uturn-v1"
DEFAULT_PEAK_WINDOW_SESSIONS = 20
DEFAULT_TOLERANCE_PCT = 3.0

REQUIRED_COLUMNS = {
    "Symbol", "Previous_FY", "Current_FY", "Previous_EPS", "Current_EPS",
    "Previous_EPS_Basis", "Current_EPS_Basis",
    "Previous_Reporting_Basis", "Current_Reporting_Basis",
    "Previous_EPS_Unit", "Current_EPS_Unit",
    "Previous_EPS_Source_URL", "Current_EPS_Source_URL",
    "Result_Announcement_Source_URL", "Result_Announcement_Date",
    "Peak_Price", "Peak_Price_Source_URL",
    "Latest_Post_Result_Close", "Latest_Post_Result_Session",
    "Latest_Post_Result_Source_URL", "EPS_Verified", "Peak_Price_Verified",
    "Corporate_Action_Adjusted",
}


def _as_date(value):
    if value is None or pd.isna(value) or str(value).strip() == "":
        return None
    try:
        return pd.Timestamp(value).date()
    except (TypeError, ValueError, OverflowError):
        return None


def _fy_end_year(value):
    """Accept FY2025, 2024-25, FY24-25 or 2025; return ending year."""
    if value is None or pd.isna(value):
        return None
    text = str(value).strip().upper().replace(" ", "")
    if text.startswith("FY"):
        text = text[2:]
    if "-" in text:
        left, right = text.split("-", 1)
        if not left.isdigit() or not right.isdigit():
            return None
        if len(right) == 2:
            return 2000 + int(right)
        return int(right)
    if text.isdigit() and len(text) == 4:
        return int(text)
    return None


def select_pre_result_peak(
    ohlc: pd.DataFrame,
    announcement_date,
    *,
    window_sessions: int = DEFAULT_PEAK_WINDOW_SESSIONS,
) -> dict:
    """Select max High from exactly the latest N supplied sessions before event.

    The caller must supply validated NSE trading-session OHLC rows. The entire
    announcement calendar date is excluded. Missing/duplicate/invalid sessions
    fail closed; this function does not infer an exchange calendar.
    """
    event_date = _as_date(announcement_date)
    if event_date is None or window_sessions < 1:
        return {"status": "WAIT_FOR_DATA", "reason": "Invalid event date or window"}
    if not isinstance(ohlc, pd.DataFrame) or not {"Date", "High"}.issubset(ohlc.columns):
        return {"status": "WAIT_FOR_DATA", "reason": "OHLC requires Date and High columns"}

    frame = ohlc.copy()
    frame["_session"] = frame["Date"].map(_as_date)
    if frame["_session"].isna().any():
        return {"status": "WAIT_FOR_DATA", "reason": "Missing or invalid OHLC session date"}
    frame = frame[frame["_session"] < event_date].sort_values("_session")

    if frame["_session"].duplicated().any():
        return {"status": "WAIT_FOR_DATA", "reason": "Duplicate pre-result OHLC session"}
    if len(frame) < window_sessions:
        return {
            "status": "WAIT_FOR_DATA",
            "reason": f"Need {window_sessions} pre-result sessions; received {len(frame)}",
        }

    selected = frame.tail(window_sessions).copy()
    highs = pd.to_numeric(selected["High"], errors="coerce")
    if highs.isna().any() or (highs <= 0).any():
        return {"status": "WAIT_FOR_DATA", "reason": "Missing or invalid High in peak window"}

    peak_index = highs.idxmax()
    peak = float(highs.loc[peak_index])
    peak_date = selected.loc[peak_index, "_session"]
    return {
        "status": "READY",
        "reason": "",
        "Peak_Price": peak,
        "Peak_Price_Date": peak_date.isoformat(),
        "Peak_Window_Start": selected["_session"].iloc[0].isoformat(),
        "Peak_Window_End": selected["_session"].iloc[-1].isoformat(),
        "Peak_Window_Sessions": int(len(selected)),
    }


def calculate_uturn_targets(
    df: pd.DataFrame,
    *,
    tolerance_pct: float = DEFAULT_TOLERANCE_PCT,
) -> pd.DataFrame:
    """Calculate a research-only valuation reset estimate for each input row.

    Diluted EPS is mandatory. Annual periods must be consecutive, both EPS
    values positive, verified and same-basis. No Basic EPS fallback is allowed.
    """
    if not 0 <= tolerance_pct < 100:
        raise ValueError("tolerance_pct must be in [0, 100)")
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    out = df.copy()
    numeric_outputs = [
        "EPS_Drop", "Reference_PE", "Expected_Correction", "U_Turn_Target",
        "Lower_Bound", "Upper_Bound",
    ]
    for column in numeric_outputs:
        out[column] = float("nan")
    out["Near_U_Turn_Support"] = False
    out["U_Turn_Status"] = "WAIT_FOR_DATA"
    out["U_Turn_Reason"] = ""
    out["Calculation_Version"] = CALCULATION_VERSION
    out["TolerancePct"] = float(tolerance_pct)

    if out["Symbol"].astype(str).str.strip().eq("").any():
        out.loc[out["Symbol"].astype(str).str.strip().eq(""), "U_Turn_Reason"] = "Missing NSE symbol"

    for index, row in out.iterrows():
        def finish(status, reason):
            out.at[index, "U_Turn_Status"] = status
            out.at[index, "U_Turn_Reason"] = reason

        symbol = str(row.get("Symbol", "")).strip()
        if not symbol:
            finish("WAIT_FOR_DATA", "Missing NSE symbol")
            continue

        previous_eps_basis = str(row.get("Previous_EPS_Basis", "")).strip().upper()
        current_eps_basis = str(row.get("Current_EPS_Basis", "")).strip().upper()
        if previous_eps_basis != "DILUTED" or current_eps_basis != "DILUTED":
            finish("WAIT_FOR_DATA", "Both financial years require diluted EPS; Basic EPS fallback is prohibited")
            continue
        previous_reporting_basis = str(row.get("Previous_Reporting_Basis", "")).strip().upper()
        current_reporting_basis = str(row.get("Current_Reporting_Basis", "")).strip().upper()
        if (previous_reporting_basis not in {"CONSOLIDATED", "STANDALONE"}
                or current_reporting_basis != previous_reporting_basis):
            finish("WAIT_FOR_DATA", "Previous/current reporting basis must match and be explicit")
            continue
        if (str(row.get("Previous_EPS_Unit", "")).strip().upper() != "INR/SHARE"
                or str(row.get("Current_EPS_Unit", "")).strip().upper() != "INR/SHARE"):
            finish("WAIT_FOR_DATA", "Both EPS observations must use INR/share")
            continue
        source_fields = [
            "Previous_EPS_Source_URL", "Current_EPS_Source_URL",
            "Result_Announcement_Source_URL", "Peak_Price_Source_URL",
            "Latest_Post_Result_Source_URL",
        ]
        if any(not str(row.get(field, "")).strip().startswith("https://") for field in source_fields):
            finish("UNVERIFIED", "One or more official filing/announcement/OHLC source URLs are missing")
            continue
        if row.get("EPS_Verified") is not True and row.get("EPS_Verified") != 1:
            finish("UNVERIFIED", "Annual diluted EPS is not verified against official filings")
            continue
        if row.get("Peak_Price_Verified") is not True and row.get("Peak_Price_Verified") != 1:
            finish("UNVERIFIED", "Pre-result peak OHLC is not verified")
            continue
        if row.get("Corporate_Action_Adjusted") is not True and row.get("Corporate_Action_Adjusted") != 1:
            finish("CORPORATE_ACTION_REVIEW_REQUIRED", "EPS/share-price corporate-action comparability is unresolved")
            continue

        previous_fy = _fy_end_year(row.get("Previous_FY"))
        current_fy = _fy_end_year(row.get("Current_FY"))
        if previous_fy is None or current_fy is None or current_fy != previous_fy + 1:
            finish("WAIT_FOR_DATA", "Financial years must be consecutive completed FYs")
            continue

        event_date = _as_date(row.get("Result_Announcement_Date"))
        post_date = _as_date(row.get("Latest_Post_Result_Session"))
        if event_date is None or post_date is None or post_date <= event_date:
            finish("WAIT_FOR_DATA", "Need result announcement date and a completed post-result session")
            continue

        try:
            previous_eps = float(row.get("Previous_EPS"))
            current_eps = float(row.get("Current_EPS"))
            peak = float(row.get("Peak_Price"))
            latest_close = float(row.get("Latest_Post_Result_Close"))
        except (TypeError, ValueError):
            finish("WAIT_FOR_DATA", "EPS and price inputs must be numeric")
            continue
        if not all(pd.notna(x) for x in (previous_eps, current_eps, peak, latest_close)):
            finish("WAIT_FOR_DATA", "EPS or price input is missing")
            continue
        if previous_eps <= 0 or current_eps <= 0:
            finish("NOT_COMPARABLE_FOR_THIS_FORMULA", "Both annual diluted EPS values must be positive")
            continue
        if peak <= 0 or latest_close <= 0:
            finish("WAIT_FOR_DATA", "Peak High and post-result Close must be positive")
            continue

        if current_eps >= previous_eps:
            finish("NO_EPS_DECLINE", "Current FY diluted EPS is equal to or above previous FY")
            continue

        eps_drop = previous_eps - current_eps
        reference_pe = peak / previous_eps
        expected_correction = eps_drop * reference_pe
        target = peak - expected_correction
        equivalent_target = peak * current_eps / previous_eps
        if abs(target - equivalent_target) > max(1e-8, abs(equivalent_target) * 1e-10):
            finish("WAIT_FOR_DATA", "Equivalent valuation formula cross-check failed")
            continue

        lower = target * (1 - tolerance_pct / 100.0)
        upper = target * (1 + tolerance_pct / 100.0)
        out.at[index, "EPS_Drop"] = eps_drop
        out.at[index, "Reference_PE"] = reference_pe
        out.at[index, "Expected_Correction"] = expected_correction
        out.at[index, "U_Turn_Target"] = target
        out.at[index, "Lower_Bound"] = lower
        out.at[index, "Upper_Bound"] = upper
        near = lower <= latest_close <= upper
        out.at[index, "Near_U_Turn_Support"] = bool(near)
        finish("NEAR_UTURN_ZONE" if near else "OUTSIDE_UTURN_ZONE",
               "Price is within estimated proximity zone" if near
               else "Valid estimate; latest close is outside estimated proximity zone")

    return out
