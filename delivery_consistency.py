"""Independent 5D/10D/20D delivery consistency intelligence.

This module is observational only. It never changes the existing 5-session
Category A/B gate, candidate membership, ranking, or rejection decisions.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
import pandas as pd

from delivery_filter import get_delivery_sessions

THRESHOLD = 60.0
OUTPUT_DIR = Path("outputs")


def _as_date(value):
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        raise ValueError(f"Invalid EOD date: {value!r}")
    return parsed.date()


def _normalise_report(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    data.columns = [str(c).strip().upper().replace(" ", "_") for c in data.columns]
    required = {"SYMBOL", "SERIES", "DELIV_PER"}
    if not required.issubset(data.columns):
        raise ValueError(f"Delivery report missing required columns: {sorted(required - set(data.columns))}")
    data["SYMBOL"] = data["SYMBOL"].astype(str).str.strip().str.upper()
    data["SERIES"] = data["SERIES"].astype(str).str.strip().str.upper()
    data["DELIV_PER"] = pd.to_numeric(data["DELIV_PER"], errors="coerce")
    data = data[
        data["SYMBOL"].ne("") & data["SYMBOL"].str.lower().ne("nan")
        & data["DELIV_PER"].between(0, 100, inclusive="both")
    ].copy()
    duplicate = data.duplicated(["SYMBOL", "SERIES"], keep=False)
    if duplicate.any():
        data = data.loc[~duplicate].copy()
    return data[["SYMBOL", "SERIES", "DELIV_PER"]]


def _classify_window(values: list[float], window: int, threshold: float) -> dict:
    valid = len(values)
    prefix = f"Delivery{window}D"
    if valid != window:
        return {
            f"{prefix}Sessions": valid,
            f"{prefix}DailyPassCount": sum(v >= threshold for v in values),
            f"{prefix}Average": float("nan"),
            f"{prefix}CategoryAStatus": "WAIT_FOR_DATA",
            f"{prefix}CategoryBStatus": "WAIT_FOR_DATA",
        }
    average = sum(values) / window
    return {
        f"{prefix}Sessions": valid,
        f"{prefix}DailyPassCount": sum(v >= threshold for v in values),
        f"{prefix}Average": average,
        f"{prefix}CategoryAStatus": "PASS_AVG_GE_60_PERCENT" if average >= threshold else "FAIL_AVG_LT_60_PERCENT",
        f"{prefix}CategoryBStatus": "PASS_EACH_DAY_GE_60_PERCENT" if all(v >= threshold for v in values) else "FAIL_AT_LEAST_ONE_DAY_LT_60_PERCENT",
    }


def build_delivery_consistency_report(
    candidates: pd.DataFrame,
    asof_date,
    sessions: list[tuple[date, pd.DataFrame]] | None = None,
    http_session=None,
    threshold: float = THRESHOLD,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return candidates enriched with observational delivery consistency fields.

    Windows are the latest 5, 10 and 20 distinct valid NSE delivery reports on
    or before EOD date. A/B are calculated independently for each window:
    A = average >= threshold; B = every day >= threshold. 20D tags use the
    number of daily observations >= threshold. Missing sessions fail closed.
    """
    if candidates is None:
        candidates = pd.DataFrame()
    if candidates.empty:
        return candidates.copy(), pd.DataFrame()

    required_candidate_cols = {"TckrSymb"}
    if not required_candidate_cols.issubset(candidates.columns):
        raise ValueError("Candidates must contain TckrSymb")

    asof = _as_date(asof_date)
    if sessions is None:
        reports = get_delivery_sessions(
            asof, required_sessions=20, max_calendar_days=60, session=http_session
        )
    else:
        reports = list(sessions)

    by_day = {}
    for day, raw in reports:
        report_day = pd.to_datetime(day, errors="coerce")
        if pd.isna(report_day):
            continue
        report_day = report_day.date()
        if report_day > asof:
            continue
        if report_day in by_day:
            continue
        by_day[report_day] = _normalise_report(raw)

    ordered_days = sorted(by_day)[-20:]
    if len(ordered_days) != 20:
        raise RuntimeError(
            f"WAIT_FOR_DATA: only {len(ordered_days)}/20 distinct valid delivery sessions "
            f"available by {asof.isoformat()}"
        )

    rows = []
    for _, candidate in candidates.iterrows():
        symbol = str(candidate.get("TckrSymb", "")).strip().upper()
        series = str(candidate.get("SctySrs", "EQ")).strip().upper()
        if not series or series.lower() == "nan":
            series = "EQ"
        values_by_day = []
        for day in ordered_days:
            report = by_day[day]
            match = report[(report["SYMBOL"] == symbol) & (report["SERIES"] == series)]
            values_by_day.append(float(match.iloc[0]["DELIV_PER"]) if len(match) == 1 else None)

        valid_values = [value for value in values_by_day if value is not None]
        record = {"TckrSymb": symbol}
        for window in (5, 10, 20):
            window_values = values_by_day[-window:]
            if any(value is None for value in window_values):
                clean_values = [value for value in window_values if value is not None]
                metrics = _classify_window(clean_values, window, threshold)
            else:
                metrics = _classify_window([float(value) for value in window_values], window, threshold)
            record.update(metrics)

        # Count only the uninterrupted >=60% run ending on the latest valid
        # report date. A missing symbol/day breaks the observable streak.
        streak = 0
        for value in reversed(values_by_day):
            if value is None or value < threshold:
                break
            streak += 1
        record["Delivery20DCurrentStreak"] = streak
        record["Delivery20DTag"] = (
            "WAIT_FOR_DATA" if len(valid_values) != 20
            else "VERY_HIGH_CONSISTENCY" if record["Delivery20DDailyPassCount"] == 20
            else "HIGH_CONSISTENCY" if record["Delivery20DDailyPassCount"] >= 18
            else "CONSISTENT" if record["Delivery20DDailyPassCount"] >= 14
            else "NORMAL"
        )
        record["Delivery20DCategoryAStatus"] = record["Delivery20DCategoryAStatus"]
        record["Delivery20DCategoryBStatus"] = record["Delivery20DCategoryBStatus"]
        record["DeliveryConsistencyAsOfDate"] = asof.isoformat()
        record["DeliveryConsistencyWindowStart"] = ordered_days[0].isoformat()
        record["DeliveryConsistencyWindowEnd"] = ordered_days[-1].isoformat()
        rows.append(record)

    report = pd.DataFrame(rows)
    enriched = candidates.copy()
    metric_columns = [column for column in report.columns if column != "TckrSymb"]
    enriched = enriched.merge(report, on="TckrSymb", how="left", validate="many_to_one")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUTPUT_DIR / f"v8_delivery_consistency_{asof.strftime('%Y%m%d')}.csv"
    report.to_csv(report_path, index=False)
    print(
        f"[DELIVERY CONSISTENCY] 20-session history={len(ordered_days)}/20; "
        f"VERY_HIGH={(report['Delivery20DTag'] == 'VERY_HIGH_CONSISTENCY').sum()}; "
        f"HIGH={(report['Delivery20DTag'] == 'HIGH_CONSISTENCY').sum()}; "
        f"CONSISTENT={(report['Delivery20DTag'] == 'CONSISTENT').sum()}; "
        f"NORMAL={(report['Delivery20DTag'] == 'NORMAL').sum()}; "
        f"report={report_path}"
    )
    return enriched, report
