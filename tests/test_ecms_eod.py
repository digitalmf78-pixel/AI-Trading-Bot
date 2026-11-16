from datetime import date
import pandas as pd
import pytest

from strategies.ecms.eod import (
    calculate_rvol, _date_from_file, _equity_rows,
    expected_latest_completed_session, classify_catalyst,
)

def _frame(symbols, volumes):
    return pd.DataFrame({
        "TckrSymb": symbols, "SctySrs": ["EQ"] * len(symbols),
        "TtlTradgVol": volumes, "ClsPric": [100] * len(symbols),
        "BizDt": ["2026-11-13"] * len(symbols),
    })

def test_rvol_uses_twenty_prior_sessions_and_passes_threshold():
    current = _frame(["AAA", "BBB"], [1500, 1499])
    history = [_frame(["AAA", "BBB"], [1000, 1000]) for _ in range(20)]
    result = calculate_rvol(current, history).set_index("TckrSymb")
    assert result.loc["AAA", "RVOL"] == 1.5
    assert result.loc["AAA", "VolumeScreenStatus"] == "PASS_RVOL_GE_1_5"
    assert result.loc["BBB", "VolumeScreenStatus"] == "BELOW_RVOL_THRESHOLD"

def test_rvol_missing_symbol_baseline_waits_not_passes():
    current = _frame(["AAA"], [5000])
    history = [_frame(["BBB"], [1000]) for _ in range(20)]
    result = calculate_rvol(current, history)
    assert pd.isna(result.loc[0, "RVOL"])
    assert result.loc[0, "VolumeScreenStatus"] == "WAIT_FOR_DATA"

def test_rvol_requires_full_twenty_sessions():
    with pytest.raises(ValueError, match="Need 20 historical sessions"):
        calculate_rvol(_frame(["AAA"], [100]), [_frame(["AAA"], [50])])

def test_filename_date_parser_is_strict():
    from pathlib import Path
    assert _date_from_file(Path("bhavcopy_20261113.csv")) == date(2026, 11, 13)
    assert _date_from_file(Path("bhavcopy_latest.csv")) is None

def test_equity_rows_keeps_supported_listed_equity_series_and_excludes_etfs():
    frame = pd.DataFrame({
        "TckrSymb": ["AAA", "BBB", "FUND"],
        "SctySrs": ["EQ", "BE", "EQ"],
        "TtlTradgVol": [1000, 2000, 3000],
        "ClsPric": [100, 200, 10],
        "ISIN": ["INE000A01001", "INE000B01001", "INF000000001"],
        "FinInstrmNm": ["AAA LTD", "BBB LTD", "AMC - FUND"],
    })
    result = _equity_rows(frame)
    assert set(result["TckrSymb"]) == {"AAA", "BBB"}


def test_official_mainboard_universe_excludes_etf_isin_prefix():
    from strategies.ecms.eod import _mainboard_company_equity_symbols

    payload = pd.DataFrame({
        "SYMBOL": ["AAA", "ETF1", "BBB"],
        "NAME OF COMPANY": ["AAA LTD", "INDEX ETF", "BBB LTD"],
        "ISIN NUMBER": ["INE000A01001", "INF000000001", "INE000B01001"],
    }).to_csv(index=False).encode("utf-8")

    from pathlib import Path
    csv_path = Path("mainboard_test_equities.csv")
    csv_path.write_bytes(payload)
    try:
        assert _mainboard_company_equity_symbols(csv_path) == {"AAA", "BBB"}
    finally:
        csv_path.unlink(missing_ok=True)


def test_official_mainboard_universe_fails_closed_without_isin_column():
    from strategies.ecms.eod import _mainboard_company_equity_symbols

    payload = pd.DataFrame({"SYMBOL": ["AAA"]}).to_csv(index=False).encode("utf-8")
    from pathlib import Path
    csv_path = Path("mainboard_test_no_isin.csv")
    csv_path.write_bytes(payload)
    try:
        with pytest.raises(RuntimeError, match="lacks symbol/ISIN columns"):
            _mainboard_company_equity_symbols(csv_path)
    finally:
        csv_path.unlink(missing_ok=True)

def test_expected_latest_completed_session_uses_ist_market_close():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    ist = ZoneInfo("Asia/Kolkata")
    assert expected_latest_completed_session(datetime(2026, 11, 13, 15, 0, tzinfo=ist)) == date(2026, 11, 12)
    assert expected_latest_completed_session(datetime(2026, 11, 13, 17, 0, tzinfo=ist)) == date(2026, 11, 13)
    assert expected_latest_completed_session(datetime(2026, 11, 14, 10, 0, tzinfo=ist)) == date(2026, 11, 13)

def test_catalyst_classifier_requires_specific_positive_signal():
    status, _ = classify_catalyst("Company announces routine board meeting")
    assert status == "NEWS_FOUND_NO_STRONG_CATALYST"
    status, _ = classify_catalyst("Company receives a work order worth INR 500 crore")
    assert status == "STRONG_POSITIVE_CATALYST_REVIEW"

def test_negative_risk_overrides_positive_headline_terms():
    status, flags = classify_catalyst("Company wins a contract but auditor resignation announced")
    assert status == "NEGATIVE_RISK_REVIEW"
    assert "auditor resignation" in flags


def test_ecms_mainboard_loader_uses_ecms_owned_cache_directory(tmp_path, monkeypatch):
    import main_board_filter
    import strategies.ecms.eod as ecms_eod

    ecms_cache = tmp_path / "data" / "cache" / "ecms" / "universe"
    csv_path = ecms_cache / "nse_main_board_equity.csv"
    csv_path.parent.mkdir(parents=True)
    pd.DataFrame({
        "SYMBOL": ["AAA", "ETF1", "BBB"],
        "NAME OF COMPANY": ["AAA LTD", "INDEX ETF", "BBB LTD"],
        "ISIN NUMBER": ["INE000A01001", "INF000000001", "INE000B01001"],
    }).to_csv(csv_path, index=False)

    captured = {}

    def fake_load_official_board_lists(session=None, cache_dir=None):
        captured["cache_dir"] = cache_dir
        return {"AAA", "ETF1", "BBB"}, {"SME1"}, {
            "main_board_source": "OFFICIAL_CACHED",
            "sme_source": "OFFICIAL_CACHED",
        }

    monkeypatch.setattr(main_board_filter, "load_official_board_lists", fake_load_official_board_lists)
    symbols, source = ecms_eod.load_official_mainboard_symbols(universe_dir=ecms_cache)

    assert symbols == {"AAA", "BBB"}
    assert captured["cache_dir"] == ecms_cache
    assert "OFFICIAL_CACHED" in source



def test_expected_latest_completed_session_rolls_weekend_and_holiday_forward(monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    import strategies.ecms.eod as ecms_eod

    ist = ZoneInfo("Asia/Kolkata")
    # Normal Friday EOD -> Friday completed session; Monday morning -> Friday.
    monkeypatch.setattr(ecms_eod, "is_trading_session", lambda day: day.weekday() < 5)
    assert ecms_eod.expected_latest_completed_session(
        datetime(2026, 11, 13, 17, 0, tzinfo=ist)
    ) == date(2026, 11, 13)
    assert ecms_eod.expected_latest_completed_session(
        datetime(2026, 11, 16, 9, 20, tzinfo=ist)
    ) == date(2026, 11, 13)
    assert ecms_eod.expected_latest_completed_session(
        datetime(2026, 11, 17, 9, 20, tzinfo=ist)
    ) == date(2026, 11, 16)

    # If Monday is an NSE holiday, Tuesday morning must still resolve to Friday.
    monkeypatch.setattr(
        ecms_eod, "is_trading_session",
        lambda day: day.weekday() < 5 and day != date(2026, 11, 16),
    )
    assert ecms_eod.expected_latest_completed_session(
        datetime(2026, 11, 17, 9, 20, tzinfo=ist)
    ) == date(2026, 11, 13)

