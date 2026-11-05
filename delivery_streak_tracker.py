"""Persistent EOD streak tracking for stocks that pass Delivery A and/or B.

Counts distinct NSE trading-session scan dates, not calendar days. Re-running
the same EOD date never increments a symbol twice. The state file lives in the
existing delivery cache directory so GitHub Actions can restore it between runs.
"""
from __future__ import annotations

import os
from pathlib import Path
import tempfile

import pandas as pd


STATE_PATH = Path("data") / "cache" / "delivery" / "v8_delivery_scan_streak_state.csv"
REPORT_PATH = Path("outputs") / "v8_delivery_scan_streak.csv"
STATE_COLUMNS = [
    "TckrSymb", "LastScanDate", "ConsecutiveAorBScanSessions",
    "TotalAorBQualifyingScanSessions", "LastQualifying", "LastDeliveryCategory",
    "LastDeliveryStatus", "LastAvgDelivery5D", "LastLatestDeliveryPct",
]
TRACKER_COLUMNS = [
    "AorBScanStreakStatus", "DeliveryCategory",
    "ConsecutiveAorBScanSessions", "TotalAorBQualifyingScanSessions",
    "FirstDateOfCurrentStreak", "LastTrackedScanDate",
]


def _date(value) -> pd.Timestamp:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return pd.NaT
    if getattr(parsed, "tzinfo", None) is not None:
        parsed = parsed.tz_convert("Asia/Kolkata").tz_localize(None)
    return parsed.normalize()


def _truth(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or pd.isna(value):
        return False
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _category(row: pd.Series) -> tuple[bool, str]:
    category_a = str(row.get("DeliveryCategoryAStatus", "")).strip().upper() == "PASS_AVG_GE_60_PERCENT"
    category_b = str(row.get("DeliveryCategoryBStatus", "")).strip().upper() == "PASS_EACH_DAY_GE_60_PERCENT"
    if category_a and category_b:
        return True, "A_AND_B"
    if category_a:
        return True, "A_ONLY"
    if category_b:
        return True, "B_ONLY"
    return False, "NONE"


def _read_state(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=STATE_COLUMNS)
    state = pd.read_csv(path)
    if not set(STATE_COLUMNS).issubset(state.columns):
        raise ValueError("delivery streak state schema is incomplete")
    state = state[STATE_COLUMNS].copy()
    state["TckrSymb"] = state["TckrSymb"].astype(str).str.strip().str.upper()
    state = state[state["TckrSymb"].ne("") & state["TckrSymb"].str.lower().ne("nan")]
    return state.drop_duplicates("TckrSymb", keep="last").reset_index(drop=True)


def _write_csv_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", suffix=".tmp",
            prefix=f".{path.name}.", dir=path.parent, delete=False,
        ) as handle:
            temp_path = Path(handle.name)
        frame.to_csv(temp_path, index=False)
        os.replace(temp_path, path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def update_delivery_scan_streak(
    delivery_audit: pd.DataFrame,
    eod_date,
    market_session_dates: list | tuple | set,
    data_available: bool = True,
) -> pd.DataFrame:
    """Add continuous A/B scan-session counts and write state/report CSVs.

    A session qualifies when the stock appears in today's post-RVOL delivery
    audit and passes either existing Category A or Category B. An absent or
    non-passing stock breaks its consecutive streak. Missing delivery data does
    not change saved state; the report labels that run WAIT_FOR_DATA.
    """
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    asof = _date(eod_date)
    if pd.isna(asof):
        raise ValueError(f"Invalid EOD scan date: {eod_date!r}")

    audit = delivery_audit.copy() if isinstance(delivery_audit, pd.DataFrame) else pd.DataFrame()
    if "TckrSymb" not in audit.columns:
        audit["TckrSymb"] = pd.Series(dtype="object")
    audit["TckrSymb"] = audit["TckrSymb"].astype(str).str.strip().str.upper()
    audit = audit[audit["TckrSymb"].ne("") & audit["TckrSymb"].str.lower().ne("nan")].copy()

    state = _read_state(STATE_PATH)
    old_by_symbol = {row["TckrSymb"]: row.to_dict() for _, row in state.iterrows()}
    current_by_symbol = {}
    duplicate_symbols = set(audit.loc[audit["TckrSymb"].duplicated(keep=False), "TckrSymb"])
    for _, row in audit.drop_duplicates("TckrSymb", keep="first").iterrows():
        current_by_symbol[row["TckrSymb"]] = row

    prior_sessions = []
    for value in market_session_dates or []:
        session = _date(value)
        if pd.notna(session) and session < asof:
            prior_sessions.append(session)
    previous_market_session = max(prior_sessions) if prior_sessions else pd.NaT

    next_rows = []
    output_rows = []
    all_symbols = sorted(set(old_by_symbol) | set(current_by_symbol))
    for symbol in all_symbols:
        old = old_by_symbol.get(symbol, {})
        current = current_by_symbol.get(symbol)
        was_qualifying, category = _category(current) if current is not None else (False, "NONE")
        if symbol in duplicate_symbols:
            was_qualifying, category = False, "NONE"

        old_date = _date(old.get("LastScanDate")) if old else pd.NaT
        old_streak = int(pd.to_numeric(pd.Series([old.get("ConsecutiveAorBScanSessions", 0)]), errors="coerce").fillna(0).iloc[0])
        old_total = int(pd.to_numeric(pd.Series([old.get("TotalAorBQualifyingScanSessions", 0)]), errors="coerce").fillna(0).iloc[0])
        old_qualifying = _truth(old.get("LastQualifying", False))
        same_scan_date = pd.notna(old_date) and old_date == asof

        if not data_available:
            streak = old_streak
            total = old_total
            last_date = old_date
            last_qualifying = old_qualifying
            last_category = str(old.get("LastDeliveryCategory", "NONE"))
            last_status = "WAIT_FOR_DATA"
            first_streak_date = old.get("FirstDateOfCurrentStreak", "")
            tracker_status = "WAIT_FOR_DATA"
        else:
            last_date = asof
            if was_qualifying:
                if same_scan_date and old_qualifying:
                    # Same EOD scan replayed; retain its already-counted streak.
                    streak, total = old_streak, old_total
                    first_streak_date = old.get("FirstDateOfCurrentStreak", str(asof.date()))
                elif not same_scan_date and old_qualifying and pd.notna(previous_market_session) and old_date == previous_market_session:
                    streak, total = old_streak + 1, old_total + 1
                    first_streak_date = old.get("FirstDateOfCurrentStreak", str(asof.date()))
                else:
                    streak, total = 1, old_total + 1
                    first_streak_date = str(asof.date())
                last_qualifying = True
                last_category = category
                last_status = "PASS_A_OR_B"
                tracker_status = "QUALIFYING_A_OR_B"
            else:
                streak, total = 0, old_total
                first_streak_date = ""
                last_qualifying = False
                last_category = "NONE"
                last_status = (
                    "DUPLICATE_SYMBOL_AMBIGUOUS" if symbol in duplicate_symbols
                    else "NOT_IN_CURRENT_RVOL_SCAN" if current is None
                    else "WAIT_FOR_DATA" if str(current.get("DeliveryStatus", "")).upper() == "WAIT_FOR_DATA"
                    else "NO_A_OR_B_PASS"
                )
                tracker_status = "WAIT_FOR_DATA" if last_status == "WAIT_FOR_DATA" else "NOT_QUALIFYING"

        state_row = {
            "TckrSymb": symbol,
            "LastScanDate": str(last_date.date()) if pd.notna(last_date) else "",
            "ConsecutiveAorBScanSessions": streak,
            "TotalAorBQualifyingScanSessions": total,
            "LastQualifying": last_qualifying,
            "LastDeliveryCategory": last_category,
            "LastDeliveryStatus": last_status,
            "LastAvgDelivery5D": current.get("AvgDelivery5D", old.get("LastAvgDelivery5D", pd.NA)) if current is not None else old.get("LastAvgDelivery5D", pd.NA),
            "LastLatestDeliveryPct": current.get("LatestDeliveryPct", old.get("LastLatestDeliveryPct", pd.NA)) if current is not None else old.get("LastLatestDeliveryPct", pd.NA),
        }
        # Keep the start date in the state so a long streak remains auditable.
        state_row["FirstDateOfCurrentStreak"] = first_streak_date
        next_rows.append(state_row)

        report_row = current.to_dict() if current is not None else {"TckrSymb": symbol}
        report_row.update({
            "AorBScanStreakStatus": tracker_status,
            "DeliveryCategory": category if was_qualifying else ("NONE" if current is not None else "NOT_IN_CURRENT_SCAN"),
            "ConsecutiveAorBScanSessions": streak,
            "TotalAorBQualifyingScanSessions": total,
            "FirstDateOfCurrentStreak": first_streak_date,
            "LastTrackedScanDate": str(last_date.date()) if pd.notna(last_date) else "",
        })
        output_rows.append(report_row)

    state_columns = STATE_COLUMNS + ["FirstDateOfCurrentStreak"]
    next_state = pd.DataFrame(next_rows, columns=state_columns)
    if data_available:
        _write_csv_atomic(next_state, STATE_PATH)

    report_columns = list(audit.columns)
    for column in TRACKER_COLUMNS:
        if column not in report_columns:
            report_columns.append(column)
    report = pd.DataFrame(output_rows, columns=report_columns)
    _write_csv_atomic(report, REPORT_PATH)
    if data_available:
        pass_count = int(report["AorBScanStreakStatus"].eq("QUALIFYING_A_OR_B").sum()) if not report.empty else 0
        longest = int(pd.to_numeric(report["ConsecutiveAorBScanSessions"], errors="coerce").fillna(0).max()) if not report.empty else 0
        print(f"[DELIVERY TRACKER] EOD={asof.date()} qualifying_A_or_B={pass_count} longest_consecutive_sessions={longest} state={STATE_PATH} report={REPORT_PATH}")
    else:
        print(f"[DELIVERY TRACKER] EOD={asof.date()} delivery data unavailable; saved streak state was not advanced.")
    return report
