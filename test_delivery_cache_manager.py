from datetime import date
from pathlib import Path

import pandas as pd

from delivery_cache_manager import (
    audit_delivery_cache,
    delivery_cache_inventory,
    prune_old_delivery_reports,
)


def _write_report(path: Path, day: date, rows: int = 40):
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({
        "DATE1": [day.strftime("%d-%b-%Y")] * rows,
        "SYMBOL": [f"STK{i:03d}" for i in range(rows)],
        "SERIES": ["EQ"] * rows,
        "DELIV_PER": [60.0] * rows,
    }).to_csv(path, index=False)


def test_delivery_cache_audit_counts_valid_sessions_in_30_calendar_days(tmp_path):
    asof = date(2026, 11, 12)
    _write_report(tmp_path / "sec_bhavdata_full_11112026.csv", date(2026, 11, 11))
    _write_report(tmp_path / "sec_bhavdata_full_09112026.csv", date(2026, 11, 9))
    inventory = delivery_cache_inventory(asof, tmp_path)
    assert inventory["window_start"] == date(2026, 10, 14)
    assert len(inventory["valid_files"]) == 2
    assert date(2026, 11, 11) in inventory["valid_files"]
    assert len(inventory["missing_sessions"]) > 0


def test_delivery_cache_rejects_wrong_internal_report_date(tmp_path):
    _write_report(tmp_path / "sec_bhavdata_full_11112026.csv", date(2026, 11, 10))
    inventory = delivery_cache_inventory(date(2026, 11, 12), tmp_path)
    assert "sec_bhavdata_full_11112026.csv" in inventory["invalid_files"]
    assert date(2026, 11, 11) in inventory["missing_sessions"]


def test_delivery_cache_pruning_keeps_streak_state_and_recent_reports(tmp_path):
    _write_report(tmp_path / "sec_bhavdata_full_01102026.csv", date(2026, 10, 1))
    _write_report(tmp_path / "sec_bhavdata_full_15102026.csv", date(2026, 10, 15))
    state = tmp_path / "v8_delivery_scan_streak_state.csv"
    state.write_text("TckrSymb,LastScanDate\nAAA,2026-11-12\n", encoding="utf-8")
    removed = prune_old_delivery_reports(date(2026, 11, 12), tmp_path)
    assert removed == ["sec_bhavdata_full_01102026.csv"]
    assert not (tmp_path / "sec_bhavdata_full_01102026.csv").exists()
    assert (tmp_path / "sec_bhavdata_full_15102026.csv").exists()
    assert state.exists()


def test_delivery_cache_audit_emits_explicit_30d_coverage(tmp_path, capsys):
    audit_delivery_cache(date(2026, 11, 12), tmp_path)
    output = capsys.readouterr().out
    assert "DELIVERY_CACHE_WINDOW=2026-10-14..2026-11-12" in output
    assert "DELIVERY_CACHE_VALID_REPORTS_30D=0" in output
