"""Compatibility adapter for the authoritative 30-calendar-day Delivery A/B rule.

The historical module name is retained for existing imports, but it no longer
implements the obsolete five-session-only eligibility rule.
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd

from delivery_filter import apply_delivery_filter, get_delivery_sessions

OUTPUT_DIR = Path("outputs")
REPORT_DIR = Path("data") / "reports"
REQUIRED_SESSIONS = 5
THRESHOLD = 60.0


def apply_delivery_categories(candidates: pd.DataFrame, asof_date, sessions=None):
    """Apply the same 30-calendar-day A OR B eligibility rule as production."""
    frame = candidates.copy() if candidates is not None else pd.DataFrame()
    if frame.empty:
        audit = frame.copy()
        for col in (
            "DeliverySessions", "AvgDelivery30D", "DeliveryMin30D",
            "CategoryAStatus", "CategoryBStatus", "DeliveryCategoryA",
            "DeliveryCategoryB", "DeliveryCategoryStatus", "DeliveryFilterStatus",
            "DeliveryStatus",
        ):
            if col not in audit.columns:
                audit[col] = pd.Series(dtype="object")
        _write_outputs(audit, audit, audit)
        return frame, audit

    reports = sessions
    if reports is None:
        reports = get_delivery_sessions(
            asof_date, required_sessions=REQUIRED_SESSIONS,
            max_calendar_days=30, collect_all=True,
        )
    qualified, audit = apply_delivery_filter(
        frame, asof_date, symbol_col="TckrSymb", series_col="SctySrs",
        minimum_average=THRESHOLD, sessions=reports,
    )
    if audit.empty:
        _write_outputs(audit, audit, audit)
        return qualified, audit

    a_pass = audit["DeliveryCategoryAStatus"].eq("PASS_ROLLING_5D_AVG_GE_60_AT_LEAST_5")
    b_pass = audit["DeliveryCategoryBStatus"].eq("PASS_DAILY_DELIVERY_GE_60_AT_LEAST_5")
    a_wait = audit["DeliveryCategoryAStatus"].astype(str).str.startswith("WAIT_FOR_DATA")
    b_wait = audit["DeliveryCategoryBStatus"].astype(str).str.startswith("WAIT_FOR_DATA")
    audit["CategoryAStatus"] = audit["DeliveryACount30DStatus"].replace({
        "PASS": "PASS", "FAIL": "FAIL",
    }).fillna("WAIT_FOR_DATA")
    audit["CategoryBStatus"] = audit["DeliveryBCount30DStatus"].replace({
        "PASS": "PASS", "FAIL": "FAIL",
    }).fillna("WAIT_FOR_DATA")
    audit["DeliveryCategoryA"] = a_pass
    audit["DeliveryCategoryB"] = b_pass
    audit["DeliveryCategoryStatus"] = [
        "WAIT_FOR_DATA" if wait else "PASS" if (a or b) else "FAIL"
        for a, b, wait in zip(a_pass, b_pass, a_wait | b_wait)
    ]
    audit["DeliveryFilterStatus"] = audit["DeliveryCategoryStatus"].map({
        "PASS": "PASS_A_OR_B", "FAIL": "FILTERED_OUT_A_AND_B",
        "WAIT_FOR_DATA": "WAIT_FOR_DATA",
    })
    category_a = audit[a_pass].copy()
    category_b = audit[b_pass].copy()
    _write_outputs(audit, category_a, category_b)
    return qualified, audit


def _write_outputs(audit, category_a=None, category_b=None):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    category_a = category_a if category_a is not None else audit.iloc[0:0].copy()
    category_b = category_b if category_b is not None else audit.iloc[0:0].copy()
    audit.to_csv(OUTPUT_DIR / "v8_delivery_categories_audit.csv", index=False)
    category_a.to_csv(OUTPUT_DIR / "v8_delivery_category_a_rolling5d_60_count5.csv", index=False)
    category_b.to_csv(OUTPUT_DIR / "v8_delivery_category_b_daily60_count5.csv", index=False)
    audit.to_csv(REPORT_DIR / "delivery_categories_audit.csv", index=False)
