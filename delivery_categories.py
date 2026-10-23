"""Two independent five-session NSE delivery categories for V8.

LIST A: average Delivery % across five valid distinct sessions >= 60%.
LIST B: each of the same five sessions individually >= 60%.
Missing/ambiguous daily observations never PASS.
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd

from delivery_filter import get_delivery_sessions

OUTPUT_DIR = Path("outputs")
REPORT_DIR = Path("data") / "reports"
REQUIRED_SESSIONS = 5
THRESHOLD = 60.0


def apply_delivery_categories(candidates: pd.DataFrame, asof_date, sessions=None):
    if candidates is None:
        candidates = pd.DataFrame()
    frame = candidates.copy()
    audit_rows = []
    if frame.empty:
        audit = frame.copy()
        for col in ["DeliverySessions", "AvgDelivery5D", "DeliveryMin5D",
                    "CategoryAStatus", "CategoryBStatus", "DeliveryCategoryA",
                    "DeliveryCategoryB", "DeliveryCategoryStatus", "DeliveryFilterStatus", "DeliveryStatus"]:
            if col not in audit.columns:
                audit[col] = pd.Series(dtype="object")
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        audit.to_csv(OUTPUT_DIR / "v8_delivery_categories_audit.csv", index=False)
        pd.DataFrame(columns=["TckrSymb"]).to_csv(OUTPUT_DIR / "v8_delivery_category_a_avg60.csv", index=False)
        pd.DataFrame(columns=["TckrSymb"]).to_csv(OUTPUT_DIR / "v8_delivery_category_b_each_day60.csv", index=False)
        audit.to_csv(REPORT_DIR / "delivery_categories_audit.csv", index=False)
        return frame, audit

    try:
        reports = sessions if sessions is not None else get_delivery_sessions(asof_date, REQUIRED_SESSIONS)
        # Require exactly five distinct sessions; don't silently use duplicates.
        reports = sorted(reports, key=lambda x: x[0])
        if len(reports) < REQUIRED_SESSIONS or len({day for day, _ in reports}) < REQUIRED_SESSIONS:
            raise RuntimeError("WAIT_FOR_DATA: five distinct valid delivery sessions required")
        reports = reports[-REQUIRED_SESSIONS:]
    except Exception as exc:
        audit = frame.copy()
        audit["DeliverySessions"] = 0
        audit["AvgDelivery5D"] = float("nan")
        audit["DeliveryMin5D"] = float("nan")
        audit["CategoryAStatus"] = "WAIT_FOR_DATA"
        audit["CategoryBStatus"] = "WAIT_FOR_DATA"
        audit["DeliveryCategoryA"] = False
        audit["DeliveryCategoryB"] = False
        audit["DeliveryCategoryStatus"] = "WAIT_FOR_DATA"
        audit["DeliveryFilterStatus"] = "WAIT_FOR_DATA"
        audit["DeliveryStatus"] = "WAIT_FOR_DATA"
        audit["DeliveryCategoryReason"] = str(exc)
        _write_outputs(audit)
        return frame.iloc[0:0].copy(), audit

    # Build per-session exact, unique EQ delivery maps.
    daily_maps = []
    dates = []
    for day, raw in reports:
        data = raw.copy()
        data.columns = [str(c).strip().upper().replace(" ", "_") for c in data.columns]
        required = {"SYMBOL", "SERIES", "DELIV_PER"}
        if not required.issubset(data.columns):
            raise RuntimeError(f"WAIT_FOR_DATA: required delivery columns missing for {day}")
        data["SYMBOL"] = data["SYMBOL"].astype(str).str.strip().str.upper()
        data["SERIES"] = data["SERIES"].astype(str).str.strip().str.upper()
        data["DELIV_PER"] = pd.to_numeric(data["DELIV_PER"], errors="coerce")
        data = data[(data["SERIES"] == "EQ") & data["DELIV_PER"].between(0, 100)]
        counts = data.groupby("SYMBOL").size()
        ambiguous = set(counts[counts != 1].index)
        if ambiguous:
            data = data[~data["SYMBOL"].isin(ambiguous)]
        daily_maps.append(data.set_index("SYMBOL")["DELIV_PER"].to_dict())
        dates.append(pd.Timestamp(day).date().isoformat())

    for _, row in frame.iterrows():
        symbol = str(row.get("TckrSymb", row.get("SYMBOL", ""))).strip().upper()
        vals = [mapping.get(symbol) for mapping in daily_maps]
        valid = [v for v in vals if v is not None and pd.notna(v)]
        count = len(valid)
        if count != REQUIRED_SESSIONS:
            avg = minimum = float("nan")
            a_status = b_status = "WAIT_FOR_DATA"
            a_pass = b_pass = False
            reason = "FIVE_VALID_DISTINCT_SESSION_VALUES_REQUIRED"
        else:
            avg = sum(valid) / REQUIRED_SESSIONS
            minimum = min(valid)
            a_pass = avg >= THRESHOLD
            b_pass = all(v >= THRESHOLD for v in valid)
            a_status = "PASS" if a_pass else "FAIL"
            b_status = "PASS" if b_pass else "FAIL"
            reason = "OK"
        rec = row.to_dict()
        rec.update({
            "DeliverySessions": count,
            "AvgDelivery5D": round(avg, 4) if pd.notna(avg) else float("nan"),
            "DeliveryMin5D": minimum,
            "CategoryAStatus": a_status,
            "CategoryBStatus": b_status,
            "DeliveryCategoryA": bool(a_pass),
            "DeliveryCategoryB": bool(b_pass),
            "DeliveryCategoryStatus": "WAIT_FOR_DATA" if count != REQUIRED_SESSIONS else ("PASS" if a_pass else "FAIL"),
            "DeliveryFilterStatus": "PASS_GE_60_PERCENT" if a_pass else ("WAIT_FOR_DATA" if count != REQUIRED_SESSIONS else "FILTERED_OUT_LT_60_PERCENT"),
            "DeliveryStatus": "PASS" if a_pass else ("WAIT_FOR_DATA" if count != REQUIRED_SESSIONS else "FILTERED_OUT_LT_60_PERCENT"),
            "DeliveryCategoryReason": reason,
        })
        for i, day in enumerate(dates, 1):
            rec[f"DeliveryDay{i}_{day}"] = vals[i-1]
        audit_rows.append(rec)

    audit = pd.DataFrame(audit_rows)
    # Category B is intentionally a subset of Category A, but both outputs are retained.
    category_a = audit[audit["CategoryAStatus"] == "PASS"].copy()
    category_b = audit[audit["CategoryBStatus"] == "PASS"].copy()
    _write_outputs(audit, category_a, category_b)
    # Main downstream pipeline uses Category A candidates; category flags identify B members.
    return category_a, audit


def _write_outputs(audit, category_a=None, category_b=None):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    if category_a is None:
        category_a = audit.iloc[0:0].copy()
    if category_b is None:
        category_b = audit.iloc[0:0].copy()
    audit.to_csv(OUTPUT_DIR / "v8_delivery_categories_audit.csv", index=False)
    category_a.to_csv(OUTPUT_DIR / "v8_delivery_category_a_avg60.csv", index=False)
    category_b.to_csv(OUTPUT_DIR / "v8_delivery_category_b_each_day60.csv", index=False)
    audit.to_csv(REPORT_DIR / "delivery_categories_audit.csv", index=False)
