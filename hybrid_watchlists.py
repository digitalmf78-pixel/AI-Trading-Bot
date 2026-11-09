"""Independent stage watchlists for NSE V8 Hybrid Strategy.

These CSVs are reporting outputs only. They never filter, score, rank, or mutate
the main scanner candidate dataframe.
"""
from pathlib import Path
import pandas as pd

OUTPUT_DIR = Path("outputs")

ACCUMULATION_PATH = OUTPUT_DIR / "v8_hybrid_potential_accumulation_watchlist.csv"
BASE_VCP_PATH = OUTPUT_DIR / "v8_hybrid_base_vcp_watchlist.csv"
BREAKOUT_PATH = OUTPUT_DIR / "v8_hybrid_breakout_ready_watchlist.csv"
ENTRY_PATH = OUTPUT_DIR / "v8_hybrid_confirmed_entry_watchlist.csv"


def _write(frame, path):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return frame


def _with_watchlist_status(frame, status_fn):
    output = frame.copy() if frame is not None else pd.DataFrame()
    if output.empty:
        output["WatchlistStatus"] = pd.Series(dtype="object")
        output["WatchlistReason"] = pd.Series(dtype="object")
        return output
    if "TckrSymb" in output.columns:
        output["TckrSymb"] = output["TckrSymb"].astype(str).str.strip().str.upper()
        duplicates = set(output.loc[output["TckrSymb"].duplicated(keep=False), "TckrSymb"])
    else:
        duplicates = set()
    statuses, reasons = [], []
    for _, row in output.iterrows():
        symbol = str(row.get("TckrSymb", "")).strip().upper()
        if symbol in duplicates:
            statuses.append("WAIT_FOR_DATA")
            reasons.append("DUPLICATE_SYMBOL_ROW_AMBIGUOUS")
        else:
            status, reason = status_fn(row)
            statuses.append(status)
            reasons.append(reason)
    output["WatchlistStatus"] = statuses
    output["WatchlistReason"] = reasons
    return output


def write_early_hybrid_watchlists(accumulation_report, vcp_report):
    """Write Accumulation and Base/VCP watchlists for every Delivery A/B name."""
    if accumulation_report is None or accumulation_report.empty:
        empty_accumulation = pd.DataFrame(columns=["TckrSymb", "AsOfDate", "WatchlistStatus", "WatchlistReason"])
        empty_base = pd.DataFrame(columns=[
            "TckrSymb", "AsOfDate", "VCPObservationStatus",
            "ContractionTransitionsObserved", "WatchlistStatus", "WatchlistReason",
        ])
        return _write(empty_accumulation, ACCUMULATION_PATH), _write(empty_base, BASE_VCP_PATH)

    accumulation = _with_watchlist_status(
        accumulation_report,
        lambda row: (
            ("ACCUMULATION_WATCH", "DELIVERY_A_B_ELIGIBLE; VCP_AND_BREAKOUT_NOT_REQUIRED")
            if str(row.get("DeliveryEvidenceStatus", "")).upper() == "OBSERVATIONS_AVAILABLE"
            else ("WAIT_FOR_DATA", "DELIVERY_QUANTITY_OR_PRICE_EVIDENCE_INCOMPLETE")
        ),
    )
    if vcp_report is None or vcp_report.empty:
        base = accumulation.copy()
        base["VCPObservationStatus"] = "WAIT_FOR_DATA"
        base["ContractionTransitionsObserved"] = pd.NA
    else:
        join_keys = ["TckrSymb"]
        if "AsOfDate" in accumulation.columns and "AsOfDate" in vcp_report.columns:
            join_keys.append("AsOfDate")
        base = accumulation.drop(columns=["WatchlistStatus", "WatchlistReason"], errors="ignore").merge(
            vcp_report, on=join_keys, how="left", suffixes=("", "_VCP")
        )
    base = _with_watchlist_status(
        base,
        lambda row: (
            ("WAIT_FOR_DATA", "VCP_RANGE_OR_VOLUME_HISTORY_INCOMPLETE")
            if str(row.get("VCPObservationStatus", "WAIT_FOR_DATA")).upper() != "COMPLETE"
            else (
                ("BASE_FORMING", "TWO_SUCCESSIVE_20D_RANGE_CONTRACTIONS_OBSERVED; NOT_VCP_CONFIRMED")
                if pd.to_numeric(pd.Series([row.get("ContractionTransitionsObserved")]), errors="coerce").iloc[0] == 2
                else ("NO_SETUP", "TWO_STEP_CONTRACTION_SEQUENCE_NOT_OBSERVED")
            )
        ),
    )
    return _write(accumulation, ACCUMULATION_PATH), _write(base, BASE_VCP_PATH)


def write_breakout_ready_watchlist(candidates):
    """Write breakout/pullback observations without affecting candidate flow."""
    def status(row):
        chase = str(row.get("ChaseStatus", "")).strip().upper()
        breakout = str(row.get("BreakoutStatus", "WAIT_FOR_DATA")).strip()
        pullback = str(row.get("PullbackStatus", "WAIT_FOR_DATA")).strip()
        if chase in {"CHASE", "CHASED"}:
            return "CHASED", "EXISTING_CHASE_FILTER_MARKED_CHASE"
        if breakout in {"Strong Breakout", "Breakout"}:
            return "BREAKOUT_CONFIRMED", "EXISTING_BREAKOUT_RULES_PASSED"
        if pullback == "Strong Pullback":
            return "PULLBACK_CONFIRMED", "EXISTING_PULLBACK_RULES_PASSED"
        if breakout == "Near Breakout" or pullback == "Possible Pullback":
            return "ENTRY_CANDIDATE", "NEAR_BREAKOUT_OR_POSSIBLE_PULLBACK_OBSERVATION"
        if breakout == "WAIT_FOR_DATA" or pullback == "WAIT_FOR_DATA":
            return "WAIT_FOR_DATA", "BREAKOUT_OR_PULLBACK_INPUTS_INCOMPLETE"
        return "NO_SETUP", "NO_BREAKOUT_OR_PULLBACK_SETUP"
    output = _with_watchlist_status(candidates, status)
    return _write(output, BREAKOUT_PATH)


def write_confirmed_entry_watchlist(candidates):
    """Expose only the existing final EOD WATCH as an entry candidate."""
    def status(row):
        chase = str(row.get("ChaseStatus", "")).strip().upper()
        if chase in {"CHASE", "CHASED"}:
            return "CHASED", "EXISTING_CHASE_FILTER_MARKED_CHASE"
        if str(row.get("EODWatchlistStatus", "")).upper() == "WAIT_FOR_DATA" or any(
            str(row.get(column, "")).upper() == "WAIT_FOR_DATA"
            for column in ("RiskControlStatus", "MandatoryConfirmationStatus", "RiskRewardStatus")
        ):
            return "WAIT_FOR_DATA", "FINAL_EOD_CONFIRMATION_DATA_INCOMPLETE"
        if (
            str(row.get("EODWatchlistStatus", "")).upper() == "WATCH"
            and str(row.get("RiskControlStatus", "")).upper() == "PASS"
            and str(row.get("MandatoryConfirmationStatus", "")).upper() == "PASS"
            and str(row.get("RiskRewardStatus", "")).upper() == "PASS"
            and str(row.get("ChaseStatus", "")).upper() == "CLEAR"
        ):
            return "ENTRY_CANDIDATE", "EXISTING_FINAL_EOD_GATES_PASSED"
        if str(row.get("EODWatchlistStatus", "")).upper() == "WAIT_FOR_DATA":
            return "WAIT_FOR_DATA", "FINAL_EOD_GATES_WAIT_FOR_DATA"
        return "NO_SETUP", "FINAL_EOD_WATCHLIST_NOT_PASSED"
    output = _with_watchlist_status(candidates, status)
    return _write(output, ENTRY_PATH)
