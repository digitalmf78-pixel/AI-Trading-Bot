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

    report, manifest = build_track2_full_mainboard_report(
        cohort, historical, delivery_sessions, ASOF, output_dir=OUT, research_pattern_requested="BOTH"
    )
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
