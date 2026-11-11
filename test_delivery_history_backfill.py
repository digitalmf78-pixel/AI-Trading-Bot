from datetime import date
from pathlib import Path

import pandas as pd
import pytest

import delivery_history_backfill as backfill


def test_price_session_dates_uses_existing_price_cache_and_latest_n(tmp_path, monkeypatch):
    for token in ["20261102", "20261103", "20261104", "20261105", "20261106"]:
        (tmp_path / f"bhavcopy_{token}.csv").write_text("placeholder")
    monkeypatch.setattr(backfill, "is_trading_session", lambda day: day.weekday() < 5)
    assert backfill.price_session_dates(tmp_path, 3) == [
        date(2026, 11, 4), date(2026, 11, 5), date(2026, 11, 6)
    ]


def test_price_session_dates_fails_if_existing_cache_is_short(tmp_path, monkeypatch):
    (tmp_path / "bhavcopy_20261106.csv").write_text("placeholder")
    monkeypatch.setattr(backfill, "is_trading_session", lambda day: True)
    with pytest.raises(RuntimeError, match="Only 1 official price-cache sessions"):
        backfill.price_session_dates(tmp_path, 200)


def test_cached_delivery_requires_matching_internal_date_and_valid_rows(tmp_path):
    path = tmp_path / "sec_bhavdata_full_06112026.csv"
    pd.DataFrame({
        "DATE1": ["06-Nov-2026"] * 60,
        "SYMBOL": [f"SYM{i:03d}" for i in range(60)],
        "SERIES": ["EQ"] * 60,
        "DELIV_PER": [65.0 + (i % 10) for i in range(60)],
    }).to_csv(path, index=False)
    ok, rows, digest = backfill._valid_cached_report(path, date(2026, 11, 6))
    assert ok and rows == 2 and len(digest) == 64


def test_cached_delivery_rejects_mismatched_internal_date(tmp_path):
    path = tmp_path / "sec_bhavdata_full_06112026.csv"
    pd.DataFrame({
        "DATE1": ["05-Nov-2026"] * 60,
        "SYMBOL": [f"SYM{i:03d}" for i in range(60)],
        "SERIES": ["EQ"] * 60,
        "DELIV_PER": [65.0] * 60,
    }).to_csv(path, index=False)
    ok, rows, digest = backfill._valid_cached_report(path, date(2026, 11, 6))
    assert not ok and rows == 0 and digest == ""


def test_backfill_summary_is_partial_if_some_reports_unavailable(tmp_path, monkeypatch):
    dates = [date(2026, 11, 5), date(2026, 11, 6)]
    monkeypatch.setattr(backfill, "price_session_dates", lambda *a, **k: dates)
    monkeypatch.setattr(backfill, "_download_report", lambda session, day, cache_dir=None: (
        ("DOWNLOADED", 2, "a" * 64, 2048) if day == dates[0] else ("HTTP_404_NOT_AVAILABLE", 0, "", 0)
    ))
    summary = backfill.run_backfill(
        price_dir=tmp_path, cache_dir=tmp_path / "delivery",
        output_dir=tmp_path / "out", target_sessions=2
    )
    assert summary["ValidDeliveryReports"] == 1
    assert summary["MissingOrRejected"] == 1
    assert summary["Status"] == "PARTIAL_DELIVERY_HISTORY"
