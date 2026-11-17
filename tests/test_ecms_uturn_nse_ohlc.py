import pandas as pd

from strategies.ecms.uturn_nse_ohlc import (
    build_nse_symbol_ohlc_window,
    extract_nse_eq_ohlc_row,
)


def _bhavcopy(date, **overrides):
    row = {
        "TradDt": pd.Timestamp(date).strftime("%Y-%m-%d"),
        "Sgmt": "CM",
        "FinInstrmTp": "STK",
        "TckrSymb": "ACI",
        "SctySrs": "EQ",
        "HghPric": 120.5,
        "ClsPric": 118.0,
        "ISIN": "INE128X01021",
    }
    row.update(overrides)
    return pd.DataFrame([row])


def _records(sessions):
    return [
        {
            "session_date": day,
            "source_url": f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{day:%Y%m%d}_F_0000.csv.zip",
            "bhavcopy": _bhavcopy(day),
        }
        for day in sessions
    ]


def test_extracts_only_nse_cash_market_eq_series():
    day = pd.Timestamp("2026-05-08")
    result = extract_nse_eq_ohlc_row(
        _bhavcopy(day), symbol="ACI", expected_session=day,
        source_url="https://nsearchives.nseindia.com/content/cm/sample.zip",
    )
    assert result["status"] == "READY"
    assert result["High"] == 120.5
    assert result["Close"] == 118.0
    assert result["ISIN"] == "INE128X01021"


def test_rejects_non_nse_source_and_duplicate_symbol_rows():
    day = pd.Timestamp("2026-05-08")
    bad_source = extract_nse_eq_ohlc_row(
        _bhavcopy(day), symbol="ACI", expected_session=day,
        source_url="https://example.com/bhavcopy.zip",
    )
    assert bad_source["status"] == "UNVERIFIED"

    duplicate = pd.concat([_bhavcopy(day), _bhavcopy(day)], ignore_index=True)
    result = extract_nse_eq_ohlc_row(
        duplicate, symbol="ACI", expected_session=day,
        source_url="https://nsearchives.nseindia.com/content/cm/sample.zip",
    )
    assert result["status"] == "WAIT_FOR_DATA"


def test_builds_exact_20_session_window_and_rejects_event_day():
    sessions = list(pd.bdate_range("2026-04-13", periods=20))
    event_date = pd.Timestamp("2026-05-12")
    result = build_nse_symbol_ohlc_window(
        _records(sessions), symbol="ACI", expected_sessions=sessions,
        announcement_date=event_date, window_sessions=20,
    )
    assert result["status"] == "READY"
    assert len(result["ohlc"]) == 20
    assert result["window_start"] == sessions[0].date().isoformat()
    assert result["window_end"] == sessions[-1].date().isoformat()

    bad_sessions = sessions[:-1] + [event_date]
    rejected = build_nse_symbol_ohlc_window(
        _records(bad_sessions), symbol="ACI", expected_sessions=bad_sessions,
        announcement_date=event_date, window_sessions=20,
    )
    assert rejected["status"] == "WAIT_FOR_DATA"


def test_missing_or_extra_session_fails_closed():
    sessions = list(pd.bdate_range("2026-04-13", periods=20))
    records = _records(sessions[:-1])
    result = build_nse_symbol_ohlc_window(
        records, symbol="ACI", expected_sessions=sessions,
        announcement_date="2026-05-12", window_sessions=20,
    )
    assert result["status"] == "WAIT_FOR_DATA"


def test_requires_same_isin_and_valid_prices_across_window():
    sessions = list(pd.bdate_range("2026-04-13", periods=20))
    records = _records(sessions)
    records[5]["bhavcopy"] = _bhavcopy(sessions[5], ISIN="INF009A01021")
    result = build_nse_symbol_ohlc_window(
        records, symbol="ACI", expected_sessions=sessions,
        announcement_date="2026-05-12", window_sessions=20,
    )
    # The extractor validates that each row is an Indian equity ISIN. Cross-row
    # ISIN consistency is checked by the window builder and must fail closed.
    assert result["status"] == "UNVERIFIED"
