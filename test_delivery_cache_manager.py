from datetime import date
from pathlib import Path

import pandas as pd
import pytest

import delivery_cache_manager as manager
from delivery_cache_manager import (
    audit_delivery_cache,
    audit_delivery_history_cache,
    delivery_cache_inventory,
    delivery_history_inventory,
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


def test_scanner_delivery_audit_remains_30_calendar_days(tmp_path):
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


def test_200_session_inventory_uses_exact_validated_bhavcopy_dates(tmp_path, monkeypatch):
    expected = [date(2026, 1, 2) + pd.Timedelta(days=i) for i in range(200)]
    expected = [pd.Timestamp(x).date() for x in expected]
    monkeypatch.setattr(manager, "price_session_dates", lambda _dir, n: expected[-n:])
    for day in expected:
        _write_report(tmp_path / f"sec_bhavdata_full_{day.strftime('%d%m%Y')}.csv", day)
    inv = delivery_history_inventory(tmp_path, Path("unused"), 200)
    assert inv["complete"] is True
    assert inv["expected_sessions"] == expected
    assert len(inv["valid_files"]) == 200


def test_200_session_inventory_reports_missing_and_invalid_without_fabrication(tmp_path, monkeypatch):
    expected = [date(2026, 1, 2) + pd.Timedelta(days=i) for i in range(200)]
    expected = [pd.Timestamp(x).date() for x in expected]
    monkeypatch.setattr(manager, "price_session_dates", lambda _dir, n: expected[-n:])
    for day in expected[:-1]:
        _write_report(tmp_path / f"sec_bhavdata_full_{day.strftime('%d%m%Y')}.csv", day)
    bad_day = expected[-2]
    _write_report(tmp_path / f"sec_bhavdata_full_{bad_day.strftime('%d%m%Y')}.csv", expected[-3])
    inv = delivery_history_inventory(tmp_path, Path("unused"), 200)
    assert inv["complete"] is False
    assert expected[-1] in inv["missing_sessions"]
    assert f"sec_bhavdata_full_{bad_day.strftime('%d%m%Y')}.csv" in inv["invalid_files"]


def test_pruning_requires_complete_200_session_coverage(tmp_path, monkeypatch):
    expected = [date(2026, 1, 2) + pd.Timedelta(days=i) for i in range(200)]
    expected = [pd.Timestamp(x).date() for x in expected]
    monkeypatch.setattr(manager, "price_session_dates", lambda _dir, n: expected[-n:])
    with pytest.raises(RuntimeError, match="Refusing to prune"):
        prune_old_delivery_reports(tmp_path, Path("unused"), 200)


def test_pruning_keeps_latest_200_and_non_session_or_invalid_files(tmp_path, monkeypatch):
    expected = [date(2026, 1, 2) + pd.Timedelta(days=i) for i in range(200)]
    expected = [pd.Timestamp(x).date() for x in expected]
    monkeypatch.setattr(manager, "price_session_dates", lambda _dir, n: expected[-n:])
    old = date(2025, 12, 31)
    _write_report(tmp_path / f"sec_bhavdata_full_{old.strftime('%d%m%Y')}.csv", old)
    for day in expected:
        _write_report(tmp_path / f"sec_bhavdata_full_{day.strftime('%d%m%Y')}.csv", day)
    state = tmp_path / "v8_delivery_scan_streak_state.csv"
    state.write_text("TckrSymb,LastScanDate\nAAA,2026-11-12\n", encoding="utf-8")
    # A malformed/non-session file is preserved for inspection, not silently deleted.
    non_session = date(2025, 12, 30)
    _write_report(tmp_path / f"sec_bhavdata_full_{non_session.strftime('%d%m%Y')}.csv", non_session)
    removed = prune_old_delivery_reports(tmp_path, Path("unused"), 200)
    assert removed == [f"sec_bhavdata_full_{old.strftime('%d%m%Y')}.csv"]
    assert not (tmp_path / f"sec_bhavdata_full_{old.strftime('%d%m%Y')}.csv").exists()
    assert (tmp_path / f"sec_bhavdata_full_{non_session.strftime('%d%m%Y')}.csv").exists()
    assert state.exists()


def test_audit_emits_explicit_200_session_coverage(tmp_path, monkeypatch, capsys):
    expected = [date(2026, 1, 2) + pd.Timedelta(days=i) for i in range(200)]
    expected = [pd.Timestamp(x).date() for x in expected]
    monkeypatch.setattr(manager, "price_session_dates", lambda _dir, n: expected[-n:])
    audit_delivery_history_cache(tmp_path, Path("unused"), 200)
    output = capsys.readouterr().out
    assert "DELIVERY_HISTORY_TARGET_SESSIONS=200" in output
    assert "DELIVERY_HISTORY_COVERAGE=0/200" in output


def test_delivery_cache_audit_emits_explicit_30d_coverage(tmp_path, capsys):
    audit_delivery_cache(date(2026, 11, 12), tmp_path)
    output = capsys.readouterr().out
    assert "DELIVERY_CACHE_WINDOW_30D=2026-10-14..2026-11-12" in output
    assert "DELIVERY_CACHE_VALID_REPORTS_30D=0" in output
