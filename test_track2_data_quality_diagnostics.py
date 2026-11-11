from datetime import date, timedelta

import pandas as pd

from delivery_quantity_analysis import build_delivery_quantity_report
from vcp_observation_analysis import build_vcp_observation_report
from nse_trading_calendar import is_trading_session


def _history_rows(symbol, dates, duplicate_first=False, missing_volume=False, invalid_ohlc=False):
    rows = []
    for index, day in enumerate(dates):
        low = 100.0 + index
        high = low + 5.0
        close = low + 2.0
        if invalid_ohlc and index == 10:
            high = low - 1.0
        volume = 1000.0 + index
        if missing_volume and index == 10:
            volume = float("nan")
        row = {
            "TckrSymb": symbol,
            "SctySrs": "EQ",
            "Date": pd.Timestamp(day),
            "HghPric": high,
            "LwPric": low,
            "ClsPric": close,
            "TtlTradgVol": volume,
        }
        rows.append(row)
        if duplicate_first and index == 0:
            rows.append(dict(row))
    return rows


def _vcp_report(tmp_path, aaa_rows, dates):
    # BBB supplies the complete market-session calendar while AAA is varied.
    historical = [
        pd.DataFrame(aaa_rows),
        pd.DataFrame(_history_rows("BBB", dates)),
    ]
    candidates = pd.DataFrame([{"TckrSymb": "AAA", "SctySrs": "EQ"}])
    return build_vcp_observation_report(
        candidates, historical, dates[-1], output_path=tmp_path / "vcp.csv"
    ).iloc[0]


def test_delivery_quantity_missing_is_not_misreported_as_malformed(tmp_path):
    sessions = []
    start = date(2026, 10, 1)
    for index in range(5):
        day = start + timedelta(days=index)
        quantity = float("nan") if index == 4 else 100 + index
        sessions.append((day, pd.DataFrame([{
            "SYMBOL": "AAA", "SERIES": "BE", "DELIV_QTY": quantity,
            "DELIV_PER": 65.0, "TTL_TRD_QNTY": 1000,
            "CLOSE_PRICE": 100.0,
        }])))
    candidates = pd.DataFrame([{"TckrSymb": "AAA", "SctySrs": "BE"}])

    report, _ = build_delivery_quantity_report(
        candidates, date(2026, 10, 5), sessions,
        output_path=tmp_path / "delivery.csv",
    )

    row = report.iloc[0]
    assert row["DeliveryQty5DStatus"] == "WAIT_FOR_DATA"
    assert row["DeliveryQty5DReason"] == "MISSING_DELIVERY_QUANTITY"
    assert row["DeliveryQty5DMissingQuantityDates"] == "2026-10-05"
    assert row["DeliveryQty5DNonfiniteQuantityDates"] == ""
    assert row["DeliveryQty5DNegativeQuantityDates"] == ""


def test_vcp_reports_missing_symbol_session_reason(tmp_path):
    dates = [day.date() for day in pd.date_range("2026-01-01", "2026-06-30", freq="D") if is_trading_session(day.date())][:60]
    rows = _history_rows("AAA", dates[1:])

    row = _vcp_report(tmp_path, rows, dates)

    assert row["VCPObservationStatus"] == "WAIT_FOR_DATA"
    assert row["VCPRangeWaitReason"] == "MISSING_SYMBOL_SESSION_ROWS"
    assert row["VCPMissingSessionCount"] == 1
    assert row["VCPAvailableSymbolSessions"] == 59


def test_vcp_reports_duplicate_symbol_session_reason(tmp_path):
    dates = [day.date() for day in pd.date_range("2026-01-01", "2026-06-30", freq="D") if is_trading_session(day.date())][:60]
    rows = _history_rows("AAA", dates, duplicate_first=True)

    row = _vcp_report(tmp_path, rows, dates)

    assert row["VCPObservationStatus"] == "WAIT_FOR_DATA"
    assert row["VCPRangeWaitReason"] == "DUPLICATE_SYMBOL_SESSION_ROWS"
    assert row["VCPDuplicateSessionCount"] == 1
    assert row["VCPSymbolWindowRows"] == 61


def test_vcp_reports_invalid_ohlc_reason(tmp_path):
    dates = [day.date() for day in pd.date_range("2026-01-01", "2026-06-30", freq="D") if is_trading_session(day.date())][:60]
    rows = _history_rows("AAA", dates, invalid_ohlc=True)

    row = _vcp_report(tmp_path, rows, dates)

    assert row["VCPObservationStatus"] == "WAIT_FOR_DATA"
    assert row["VCPRangeWaitReason"] == "INVALID_OHLC_VALUES"
    assert row["VCPInvalidOHLCRowCount"] == 1


def test_vcp_reports_missing_volume_separately_from_range(tmp_path):
    dates = [day.date() for day in pd.date_range("2026-01-01", "2026-06-30", freq="D") if is_trading_session(day.date())][:60]
    rows = _history_rows("AAA", dates, missing_volume=True)

    row = _vcp_report(tmp_path, rows, dates)

    assert row["VCPRangeObservationStatus"] == "COMPLETE"
    assert row["VCPVolumeObservationStatus"] == "WAIT_FOR_DATA"
    assert row["VCPVolumeWaitReason"] == "MISSING_VOLUME_VALUES"
    assert row["VCPMissingVolumeRowCount"] == 1
    assert row["VCPObservationStatus"] == "PARTIAL_DATA"
