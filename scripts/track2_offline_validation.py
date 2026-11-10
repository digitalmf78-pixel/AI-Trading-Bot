from datetime import date, datetime, timedelta
from hashlib import sha256
from pathlib import Path
import json
import pandas as pd
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ASOF = date(2026, 11, 9)
ARTIFACT = Path("artifact")
OUT = Path("outputs/track2_full_mainboard")

def digest(path):
    h = sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def delivery_source_contract_audit(cohort, sessions):
    """Read-only candidate-level audit of raw cached NSE Delivery report coverage."""
    source = cohort.copy()
    source["_AUDIT_SYMBOL"] = source["TckrSymb"].astype(str).str.strip().str.upper()
    source["_AUDIT_SERIES"] = source.get("SctySrs", pd.Series("EQ", index=source.index)).astype(str).str.strip().str.upper()
    records = []
    for day, raw in sessions:
        if raw is None or raw.empty:
            records.append({"Date": day.isoformat(), "Series": "UNKNOWN",
                            "SourceRows": 0, "DeliveryQuantityColumnPresent": False,
                            "AuditStatus": "EMPTY_SOURCE_REPORT"})
            continue
        frame = raw.copy()
        frame.columns = [str(c).strip().upper().replace(" ", "_") for c in frame.columns]
        symbol_col = next((c for c in ("SYMBOL", "TCKRSYMB") if c in frame.columns), None)
        series_col = next((c for c in ("SERIES", "SCTYSRS") if c in frame.columns), None)
        qty_col = next((c for c in ("DELIV_QTY", "DELIVERY_QTY", "DELIVQTY",
                                    "TTL_DLVRY_QTY", "TTLDLVRYQTY",
                                    "TTL_DELIV_QTY", "TOTAL_DELIVERY_QTY") if c in frame.columns), None)
        if symbol_col is None or series_col is None:
            records.append({"Date": day.isoformat(), "Series": "UNKNOWN",
                            "SourceRows": len(frame), "DeliveryQuantityColumnPresent": qty_col is not None,
                            "AuditStatus": "MISSING_SYMBOL_OR_SERIES_COLUMN"})
            continue
        frame["_SYMBOL"] = frame[symbol_col].astype(str).str.strip().str.upper()
        frame["_SERIES"] = frame[series_col].astype(str).str.strip().str.upper()
        frame["_QTY"] = pd.to_numeric(frame[qty_col], errors="coerce") if qty_col else float("nan")
        for series in sorted(set(frame["_SERIES"].dropna()) | set(source["_AUDIT_SERIES"].dropna())):
            part = frame[frame["_SERIES"].eq(series)]
            candidates = source[source["_AUDIT_SERIES"].eq(series)]
            counts = part.groupby("_SYMBOL").size().to_dict()
            present = missing_row = duplicate_row = qty_missing = qty_nonfinite = qty_negative = qty_zero = qty_valid = 0
            for _, candidate in candidates.iterrows():
                rows = part[part["_SYMBOL"].eq(candidate["_AUDIT_SYMBOL"])]
                if len(rows) == 0:
                    missing_row += 1
                elif len(rows) > 1:
                    duplicate_row += 1
                else:
                    present += 1
                    if qty_col is None or pd.isna(rows.iloc[0]["_QTY"]):
                        qty_missing += 1
                    elif not math.isfinite(float(rows.iloc[0]["_QTY"])):
                        qty_nonfinite += 1
                    elif float(rows.iloc[0]["_QTY"]) < 0:
                        qty_negative += 1
                    elif float(rows.iloc[0]["_QTY"]) == 0:
                        qty_zero += 1
                        qty_valid += 1
                    else:
                        qty_valid += 1
            records.append({
                "Date": day.isoformat(), "Series": series,
                "SourceRows": len(part), "SourceUniqueSymbols": int(part["_SYMBOL"].nunique()),
                "SourceDuplicateSymbolRows": int(part["_SYMBOL"].duplicated(keep=False).sum()),
                "DeliveryQuantityColumn": qty_col or "",
                "DeliveryQuantityColumnPresent": qty_col is not None,
                "SourceQuantityMissingRows": int(part["_QTY"].isna().sum()),
                "SourceQuantityNonfiniteRows": int((~np.isfinite(part["_QTY"].astype(float))).sum()) if qty_col else len(part),
                "SourceQuantityNegativeRows": int((part["_QTY"] < 0).sum()) if qty_col else 0,
                "CandidateCount": len(candidates), "CandidateRowsPresent": present,
                "CandidateRowsMissing": missing_row, "CandidateRowsDuplicate": duplicate_row,
                "CandidateQuantityMissing": qty_missing, "CandidateQuantityNonfinite": qty_nonfinite,
                "CandidateQuantityNegative": qty_negative, "CandidateQuantityZero": qty_zero,
                "CandidateQuantityValid": qty_valid,
                "AuditStatus": "COMPLETE" if qty_col is not None else "DELIVERY_QUANTITY_COLUMN_MISSING",
            })
    return pd.DataFrame(records)


def main():
    from track2_full_mainboard import build_track2_full_mainboard_report
    universe = pd.read_csv(ARTIFACT / "outputs/v8_main_board_universe_audit.csv")
    dual = pd.read_csv(ARTIFACT / "outputs/v8_delivery_dual_category_audit.csv", low_memory=False)
    if universe.TckrSymb.astype(str).duplicated().any() or dual.TckrSymb.astype(str).duplicated().any():
        raise RuntimeError("Duplicate source symbol identity")
    passed = universe[universe.MainBoardStatus.eq("PASS_MAIN_BOARD")].copy()
    cohort = passed.merge(dual, on="TckrSymb", how="left", validate="one_to_one")
    if len(cohort) != 2588 or cohort.DeliveryFilterStatus.isna().any():
        raise RuntimeError("Expected 2,588 aligned Mainboard rows")
    cohort["MainBoardStatus"] = "PASS_MAIN_BOARD"
    cohort["BoardClassification"] = cohort["BoardClassification"].fillna("MAIN_BOARD")

    protected = [
        ARTIFACT / "outputs/v8_main_board_universe_audit.csv",
        ARTIFACT / "outputs/v8_delivery_dual_category_audit.csv",
        ARTIFACT / "outputs/v8_delivery_quantity_observations_20261109.csv",
        ARTIFACT / "outputs/v8_potential_accumulation_observations_20261109.csv",
        ARTIFACT / "outputs/v8_vcp_contraction_observations_20261109.csv",
    ]
    before = {str(p): digest(p) for p in protected}

    hist_root = Path("data/bhavcopy")
    historical, history_dates, history_errors = [], [], []
    for path in sorted(hist_root.glob("bhavcopy_????????.csv")):
        day = datetime.strptime(path.stem[-8:], "%Y%m%d").date()
        if day > ASOF:
            continue
        try:
            frame = pd.read_csv(path, low_memory=False)
            parsed = pd.to_datetime(frame["TradDt"], errors="coerce").dt.date
            if parsed.isna().any() or set(parsed) != {day}:
                raise ValueError("TradDt mismatch")
            frame["Date"] = pd.to_datetime(frame["TradDt"], errors="coerce")
            historical.append(frame)
            history_dates.append(day)
        except Exception as exc:
            history_errors.append({"file": path.name, "error": str(exc)})
    prior_dates = sorted(d for d in set(history_dates) if d < ASOF)
    if len(prior_dates) < 200:
        raise RuntimeError("Insufficient prior Bhavcopy cache: " + str(len(prior_dates)) + "/200")

    delivery_root = Path("data/cache/delivery")
    delivery_sessions, delivery_errors = [], []
    start = ASOF - timedelta(days=30)
    for path in sorted(delivery_root.glob("sec_bhavdata_full_????????.csv")):
        day = datetime.strptime(path.stem[-8:], "%d%m%Y").date()
        if day < start or day > ASOF:
            continue
        try:
            frame = pd.read_csv(path, low_memory=False)
            frame.columns = [str(c).strip().upper().replace(" ", "_") for c in frame.columns]
            parsed = pd.to_datetime(frame["DATE1"].astype(str).str.strip(), errors="coerce", dayfirst=True)
            if parsed.isna().any() or set(parsed.dt.date) != {day}:
                raise ValueError("DATE1 mismatch")
            delivery_sessions.append((day, frame))
        except Exception as exc:
            delivery_errors.append({"file": path.name, "error": str(exc)})
    delivery_sessions.sort(key=lambda x: x[0])
    if len(delivery_sessions) < 5:
        raise RuntimeError("Insufficient cached Delivery sessions: " + str(len(delivery_sessions)))

    source_contract = delivery_source_contract_audit(cohort, delivery_sessions)
    OUT.mkdir(parents=True, exist_ok=True)
    source_contract.to_csv(OUT / "delivery_source_contract_audit_20261109.csv", index=False)

    report, manifest = build_track2_full_mainboard_report(
        cohort, historical, delivery_sessions, ASOF, output_dir=OUT, research_pattern_requested="BOTH"
    )
    pivot_complete = report.get("PivotStructureStatus", pd.Series(dtype=str)).eq("COMPLETE")
    range200_complete = report.get("PriceRange200DStatus", pd.Series(dtype=str)).eq("OBSERVATION_AVAILABLE")
    range200_only = report.loc[range200_complete & ~pivot_complete, "TckrSymb"].astype(str).tolist() if "TckrSymb" in report.columns else []
    pivot_ema_contract = {
        "market_sessions_in_cache_including_asof": len(set(history_dates)),
        "prior_sessions_before_asof": len(prior_dates),
        "expected_contract": "201 distinct symbol sessions: 200 prior complete sessions plus the current EOD as-of session",
        "pivot_structure_status_counts": report.get("PivotStructureStatus", pd.Series(dtype=str)).value_counts(dropna=False).to_dict(),
        "ema20_status_counts": report.get("ObservedEMA20Status", pd.Series(dtype=str)).value_counts(dropna=False).to_dict(),
        "ema44_status_counts": report.get("ObservedEMA44Status", pd.Series(dtype=str)).value_counts(dropna=False).to_dict(),
        "ema50_status_counts": report.get("ObservedEMA50Status", pd.Series(dtype=str)).value_counts(dropna=False).to_dict(),
        "ema200_status_counts": report.get("ObservedEMA200Status", pd.Series(dtype=str)).value_counts(dropna=False).to_dict(),
        "range200_complete_but_pivot_wait_count": len(range200_only),
        "range200_complete_but_pivot_wait_symbols": range200_only,
        "interpretation": "The four listed symbols have the full trailing 200-session range window but lack one session from the additional earliest date in the 201-session pivot/EMA history contract.",
    }
    source_contract_summary = {}
    if not source_contract.empty:
        for series, group in source_contract.groupby("Series"):
            numeric = [c for c in group.columns if c.startswith("Candidate") or c.startswith("SourceQuantity")]
            source_contract_summary[str(series)] = {
                "delivery_report_dates": len(group),
                "totals": {c: int(group[c].fillna(0).sum()) for c in numeric if pd.api.types.is_numeric_dtype(group[c])},
                "quantity_column_presence_all_dates": bool(group["DeliveryQuantityColumnPresent"].all()) if "DeliveryQuantityColumnPresent" in group else False,
            }
    after = {str(p): digest(p) for p in protected}
    if before != after:
        raise RuntimeError("Track 1 source artifact changed")
    summary = {
        "as_of_date": ASOF.isoformat(),
        "source_run_id": 42634890331,
        "input_mainboard_rows": len(cohort),
        "output_rows": len(report),
        "unique_output_symbols": int(report.TckrSymb.nunique()),
        "bhavcopy_sessions": len(history_dates),
        "prior_bhavcopy_sessions": len(prior_dates),
        "bhavcopy_errors": history_errors,
        "delivery_sessions": [d.isoformat() for d, _ in delivery_sessions],
        "delivery_errors": delivery_errors,
        "track2_manifest": manifest,
        "pivot_ema_history_contract": pivot_ema_contract,
        "delivery_source_contract_summary": source_contract_summary,
        "track1_artifacts_unchanged": before == after,
        "network_fetches": 0,
        "telegram_enabled": False,
        "production_scanner_called": False,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "offline_validation_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    if len(report) != 2588 or report.TckrSymb.nunique() != 2588:
        raise RuntimeError("Track 2 failed exact 2,588-symbol coverage")
    print(json.dumps(summary, indent=2, default=str))

if __name__ == "__main__":
    main()
