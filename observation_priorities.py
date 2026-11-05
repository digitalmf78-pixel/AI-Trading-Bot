"""Priority tiers for EOD scanner observation; these are not trade signals."""
from __future__ import annotations

from pathlib import Path

import pandas as pd


OUTPUT_PATH = Path("outputs") / "v8_observation_priority_report.csv"
A_PASS = "PASS_AVG_GE_60_PERCENT"
B_PASS = "PASS_EACH_DAY_GE_60_PERCENT"


def build_observation_priority_report(
    fundamental_audit: pd.DataFrame,
    eod_date,
    write: bool = True,
) -> pd.DataFrame:
    """Return all current Delivery A/B scanner names with conservative P1-P4 tiers.

    P1/P2 require an explicit verified fundamental PASS and an explicit peer
    relative valuation status. Missing valuation data can never promote a name.
    P3 is a Category B observation with no verified fundamental FAIL. P4 is a
    Category A-only or explicitly failed/overvalued observation.
    Every row remains observation-only; no tier is a buy recommendation.
    """
    frame = fundamental_audit.copy() if isinstance(fundamental_audit, pd.DataFrame) else pd.DataFrame()
    if "TckrSymb" not in frame.columns:
        frame["TckrSymb"] = pd.Series(dtype="object")
    frame["TckrSymb"] = frame["TckrSymb"].astype(str).str.strip().str.upper()
    frame = frame[frame["TckrSymb"].ne("") & frame["TckrSymb"].str.lower().ne("nan")].copy()
    frame = frame.drop_duplicates("TckrSymb", keep="first").reset_index(drop=True)

    a = frame.get("DeliveryCategoryAStatus", pd.Series("", index=frame.index)).fillna("").astype(str).eq(A_PASS)
    b = frame.get("DeliveryCategoryBStatus", pd.Series("", index=frame.index)).fillna("").astype(str).eq(B_PASS)
    frame = frame.loc[a | b].copy().reset_index(drop=True)
    a = frame.get("DeliveryCategoryAStatus", pd.Series("", index=frame.index)).fillna("").astype(str).eq(A_PASS)
    b = frame.get("DeliveryCategoryBStatus", pd.Series("", index=frame.index)).fillna("").astype(str).eq(B_PASS)

    fundamental = frame.get("FundamentalShortlistStatus", pd.Series("WAIT_FOR_DATA", index=frame.index)).fillna("WAIT_FOR_DATA").astype(str).str.upper()
    valuation_col = next((col for col in ("ValuationRelativePEStatus", "PeerRelativePEStatus", "RelativePEStatus") if col in frame.columns), None)
    valuation = frame[valuation_col].fillna("DATA_INSUFFICIENT").astype(str).str.upper() if valuation_col else pd.Series("DATA_INSUFFICIENT", index=frame.index)
    tiers, reasons = [], []
    for idx in frame.index:
        if fundamental.loc[idx] == "PASS" and valuation.loc[idx] == "RELATIVELY_UNDERVALUED":
            tiers.append("P1")
            reasons.append("Verified strong fundamentals and relative undervaluation; observation priority only.")
        elif fundamental.loc[idx] == "PASS" and valuation.loc[idx] == "FAIRLY_VALUED":
            tiers.append("P2")
            reasons.append("Verified strong fundamentals and fair peer valuation; observation priority only.")
        elif b.loc[idx] and fundamental.loc[idx] != "FAIL":
            tiers.append("P3")
            if fundamental.loc[idx] != "PASS":
                reasons.append("Category B delivery; fundamental verification is pending or incomplete.")
            else:
                reasons.append("Category B delivery; peer valuation verification is unavailable.")
        else:
            tiers.append("P4")
            if fundamental.loc[idx] == "FAIL":
                reasons.append("Fundamental assessment failed; keep only for low-priority observation.")
            elif valuation.loc[idx] == "RELATIVELY_OVERVALUED":
                reasons.append("Peer valuation is relatively expensive; low-priority observation.")
            else:
                reasons.append("Category A only or required verification is incomplete; low-priority observation.")

    frame["ObservationDate"] = pd.to_datetime(eod_date, errors="coerce")
    frame["ObservationPriority"] = tiers
    frame["ObservationPriorityReason"] = reasons
    frame["ObservationOnly"] = True
    frame["TradeSignal"] = "NONE"
    if "ConsecutiveAorBScanSessions" not in frame.columns:
        frame["ConsecutiveAorBScanSessions"] = 1
    frame["ConsecutiveAorBScanSessions"] = pd.to_numeric(frame["ConsecutiveAorBScanSessions"], errors="coerce").fillna(0).astype(int)

    tier_order = {"P1": 1, "P2": 2, "P3": 3, "P4": 4}
    frame["_tier_order"] = frame["ObservationPriority"].map(tier_order)
    sort_cols = ["_tier_order", "ConsecutiveAorBScanSessions"]
    ascending = [True, False]
    if "FundamentalScore" in frame.columns:
        frame["FundamentalScore"] = pd.to_numeric(frame["FundamentalScore"], errors="coerce")
        sort_cols.append("FundamentalScore")
        ascending.append(False)
    frame = frame.sort_values(sort_cols, ascending=ascending, na_position="last", kind="stable").drop(columns="_tier_order").reset_index(drop=True)
    frame["ObservationDate"] = frame["ObservationDate"].dt.strftime("%Y-%m-%d").fillna(str(eod_date))
    if write:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(OUTPUT_PATH, index=False)
    return frame
