"""Persistent 30-calendar-day Delivery history for A/B-qualified stocks.

This is a derived rolling snapshot. Raw official NSE reports remain untouched.
One row represents one validated (as-of date, symbol, series, report date)
observation. Missing quantities remain null; no observations are synthesized.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
import os

import pandas as pd

CACHE_PATH = Path("data/cache/delivery/ab_qualified_delivery_history.csv")
REQUIRED_RAW = {"SYMBOL", "SERIES", "DATE1", "DELIV_QTY", "DELIV_PER"}
A_PASS = "PASS_ROLLING_5D_AVG_GE_60_AT_LEAST_5"
B_PASS = "PASS_DAILY_DELIVERY_GE_60_AT_LEAST_5"


def _as_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return pd.Timestamp(value).date()


def build_ab_qualified_history(audit: pd.DataFrame, sessions, asof_date) -> pd.DataFrame:
    """Build long-form daily observations for the exact A OR B passing cohort."""
    asof = _as_date(asof_date)
    start = asof - timedelta(days=29)
    if audit is None or audit.empty:
        return pd.DataFrame(columns=[
            "AsOfDate", "WindowStartDate", "WindowEndDate", "Symbol", "Series",
            "ReportDate", "DELIV_QTY", "DELIV_PER", "DeliveryMembership",
            "DeliveryCategoryAStatus", "DeliveryCategoryBStatus",
            "DeliverySessions", "DeliveryACount30DDisplay", "DeliveryBCount30DDisplay",
        ])
    required_audit = {"TckrSymb", "DeliveryCategoryAStatus", "DeliveryCategoryBStatus"}
    missing = required_audit - set(audit.columns)
    if missing:
        raise ValueError(f"A/B audit missing required columns: {sorted(missing)}")

    cohort = audit.copy()
    a_pass = cohort["DeliveryCategoryAStatus"].eq(A_PASS)
    b_pass = cohort["DeliveryCategoryBStatus"].eq(B_PASS)
    cohort = cohort.loc[a_pass | b_pass].copy()
    if cohort.empty:
        return pd.DataFrame(columns=[
            "AsOfDate", "WindowStartDate", "WindowEndDate", "Symbol", "Series",
            "ReportDate", "DELIV_QTY", "DELIV_PER", "DeliveryMembership",
            "DeliveryCategoryAStatus", "DeliveryCategoryBStatus",
            "DeliverySessions", "DeliveryACount30DDisplay", "DeliveryBCount30DDisplay",
        ])

    cohort["Symbol"] = cohort["TckrSymb"].astype(str).str.strip().str.upper()
    series_source = cohort["SctySrs"] if "SctySrs" in cohort.columns else (
        cohort["SERIES"] if "SERIES" in cohort.columns else pd.Series("EQ", index=cohort.index)
    )
    cohort["Series"] = series_source.astype(str).str.strip().str.upper()
    cohort["DeliveryMembership"] = [
        "A_AND_B" if a and b else "A_ONLY" if a else "B_ONLY"
        for a, b in zip(a_pass.loc[cohort.index], b_pass.loc[cohort.index])
    ]
    # One identity per symbol+series; ambiguity is a data-integrity error.
    if cohort.duplicated(["Symbol", "Series"]).any():
        raise ValueError("A/B audit contains duplicate Symbol+Series identities")

    metadata_cols = [
        "Symbol", "Series", "DeliveryMembership", "DeliveryCategoryAStatus",
        "DeliveryCategoryBStatus",
    ]
    for source, target in (
        ("DeliverySessions", "DeliverySessions"),
        ("DeliveryACount30DDisplay", "DeliveryACount30DDisplay"),
        ("DeliveryBCount30DDisplay", "DeliveryBCount30DDisplay"),
        ("DeliveryDailyPassCount", "DeliveryDailyPassCount"),
        ("DeliveryARolling5DPassCount30D", "DeliveryARolling5DPassCount30D"),
        ("DeliveryLatestReportDate", "DeliveryLatestReportDate"),
        ("DeliveryReportAgeDays", "DeliveryReportAgeDays"),
    ):
        if source in cohort.columns:
            cohort[target] = cohort[source]
            metadata_cols.append(target)
    lookup = cohort.set_index(["Symbol", "Series"])[metadata_cols[2:]].to_dict("index")

    records = []
    seen_dates = set()
    for report_day, raw in sorted(sessions, key=lambda item: _as_date(item[0])):
        day = _as_date(report_day)
        if day < start or day > asof:
            continue
        if day in seen_dates:
            raise ValueError(f"Duplicate Delivery report date in supplied sessions: {day}")
        seen_dates.add(day)
        frame = raw.copy()
        frame.columns = [str(c).strip().upper().replace(" ", "_") for c in frame.columns]
        missing_raw = REQUIRED_RAW - set(frame.columns)
        if missing_raw:
            raise ValueError(f"Delivery report {day} missing columns: {sorted(missing_raw)}")
        parsed = pd.to_datetime(frame["DATE1"].astype(str).str.strip(), errors="coerce", dayfirst=True)
        if parsed.isna().any() or set(parsed.dt.date.tolist()) != {day}:
            raise ValueError(f"Delivery report internal DATE1 mismatch for {day}")
        frame["SYMBOL"] = frame["SYMBOL"].astype(str).str.strip().str.upper()
        frame["SERIES"] = frame["SERIES"].astype(str).str.strip().str.upper()
        frame["DELIV_PER"] = pd.to_numeric(frame["DELIV_PER"], errors="coerce")
        frame["DELIV_QTY"] = pd.to_numeric(frame["DELIV_QTY"], errors="coerce")
        frame = frame[frame["DELIV_PER"].between(0, 100, inclusive="both")]
        if frame.duplicated(["SYMBOL", "SERIES"]).any():
            raise ValueError(f"Duplicate Symbol+Series rows in validated Delivery report {day}")
        frame = frame[frame.apply(lambda r: (r["SYMBOL"], r["SERIES"]) in lookup, axis=1)]
        for row in frame.itertuples(index=False):
            values = row._asdict()
            key = (values["SYMBOL"], values["SERIES"])
            meta = lookup[key]
            records.append({
                "AsOfDate": asof.isoformat(),
                "WindowStartDate": start.isoformat(),
                "WindowEndDate": asof.isoformat(),
                "Symbol": key[0],
                "Series": key[1],
                "ReportDate": day.isoformat(),
                "DELIV_QTY": values["DELIV_QTY"],
                "DELIV_PER": values["DELIV_PER"],
                **meta,
                "ObservationStatus": "VALID_DELIVERY_PERCENT",
            })
    result = pd.DataFrame(records)
    if result.empty:
        return result
    if result.duplicated(["AsOfDate", "Symbol", "Series", "ReportDate"]).any():
        raise ValueError("Derived A/B Delivery history contains duplicate observation keys")
    return result.sort_values(["Symbol", "Series", "ReportDate"]).reset_index(drop=True)


def persist_ab_qualified_history(audit: pd.DataFrame, sessions, asof_date,
                                 path: Path = CACHE_PATH) -> pd.DataFrame:
    """Atomically replace the current rolling 30-calendar-day A/B snapshot."""
    result = build_ab_qualified_history(audit, sessions, asof_date)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + ".tmp")
    result.to_csv(temp_path, index=False)
    os.replace(temp_path, path)
    print(
        f"[DELIVERY A/B HISTORY] AsOf={_as_date(asof_date)} "
        f"qualified_symbols={result[['Symbol', 'Series']].drop_duplicates().shape[0] if not result.empty else 0} "
        f"daily_observations={len(result)} path={path}"
    )
    return result
