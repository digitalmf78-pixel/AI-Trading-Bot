"""Official NSE UDiFF bhavcopy parser for ECMS U-Turn research.

No network access is performed here. Callers must provide downloaded daily NSE
CM UDiFF bhavcopy tables and the exact official exchange-session dates.
"""
from __future__ import annotations

import pandas as pd

REQUIRED_UDIFF_COLUMNS = {
    "TradDt", "Sgmt", "FinInstrmTp", "TckrSymb", "SctySrs",
    "HghPric", "ClsPric", "ISIN",
}


def _session_date(value):
    try:
        if value is None or pd.isna(value):
            return None
        return pd.Timestamp(value).date()
    except (TypeError, ValueError, OverflowError):
        return None


def extract_nse_eq_ohlc_row(
    bhavcopy: pd.DataFrame,
    *,
    symbol: str,
    expected_session,
    source_url: str,
) -> dict:
    """Extract one verified NSE cash EQ row from a single UDiFF bhavcopy."""
    session = _session_date(expected_session)
    if session is None:
        return {"status": "WAIT_FOR_DATA", "reason": "Invalid expected NSE session"}
    if not str(source_url).startswith("https://nsearchives.nseindia.com/"):
        return {"status": "UNVERIFIED", "reason": "Source URL is not an NSE archive URL"}
    if not isinstance(bhavcopy, pd.DataFrame) or not REQUIRED_UDIFF_COLUMNS.issubset(bhavcopy.columns):
        return {"status": "WAIT_FOR_DATA", "reason": "UDiFF bhavcopy schema is incomplete"}

    frame = bhavcopy.copy()
    frame["TradDt"] = frame["TradDt"].map(_session_date)
    rows = frame[
        (frame["TradDt"] == session)
        & (frame["Sgmt"].astype(str).str.upper() == "CM")
        & (frame["FinInstrmTp"].astype(str).str.upper() == "STK")
        & (frame["TckrSymb"].astype(str).str.upper() == str(symbol).strip().upper())
        & (frame["SctySrs"].astype(str).str.upper() == "EQ")
    ]
    if len(rows) != 1:
        return {
            "status": "WAIT_FOR_DATA",
            "reason": f"Expected exactly one {symbol} CM/STK/EQ row for {session}; found {len(rows)}",
        }

    row = rows.iloc[0]
    high = pd.to_numeric(pd.Series([row["HghPric"]]), errors="coerce").iloc[0]
    close = pd.to_numeric(pd.Series([row["ClsPric"]]), errors="coerce").iloc[0]
    if pd.isna(high) or pd.isna(close) or high <= 0 or close <= 0 or close > high:
        return {"status": "WAIT_FOR_DATA", "reason": "Invalid NSE High/Close values"}
    isin = str(row["ISIN"]).strip().upper()
    if not isin.startswith("INE") or len(isin) != 12:
        return {"status": "UNVERIFIED", "reason": "Missing or invalid Indian equity ISIN"}

    return {
        "status": "READY",
        "reason": "",
        "Symbol": str(symbol).strip().upper(),
        "Date": session.isoformat(),
        "High": float(high),
        "Close": float(close),
        "ISIN": isin,
        "SourceURL": source_url,
        "Series": "EQ",
        "Segment": "CM",
        "InstrumentType": "STK",
    }


def build_nse_symbol_ohlc_window(
    records: list[dict],
    *,
    symbol: str,
    expected_sessions,
    announcement_date,
    window_sessions: int = 20,
) -> dict:
    """Build exactly N dated OHLC rows; missing/duplicate sessions fail closed.

    expected_sessions must be supplied from a verified NSE trading calendar.
    Each record is {session_date, source_url, bhavcopy}.
    """
    event_date = _session_date(announcement_date)
    sessions = [_session_date(value) for value in expected_sessions]
    if event_date is None or window_sessions < 1:
        return {"status": "WAIT_FOR_DATA", "reason": "Invalid announcement date or window"}
    if len(sessions) != window_sessions or any(value is None for value in sessions):
        return {"status": "WAIT_FOR_DATA", "reason": f"Expected exactly {window_sessions} valid NSE sessions"}
    if len(set(sessions)) != len(sessions):
        return {"status": "WAIT_FOR_DATA", "reason": "Duplicate expected NSE session"}
    if any(value >= event_date for value in sessions):
        return {"status": "WAIT_FOR_DATA", "reason": "Peak window must end strictly before result announcement date"}
    if sessions != sorted(sessions):
        return {"status": "WAIT_FOR_DATA", "reason": "Expected NSE sessions must be chronological"}

    by_date = {}
    for record in records:
        if not isinstance(record, dict):
            return {"status": "WAIT_FOR_DATA", "reason": "Invalid bhavcopy record"}
        session = _session_date(record.get("session_date"))
        if session is None or session in by_date:
            return {"status": "WAIT_FOR_DATA", "reason": "Missing or duplicate bhavcopy session"}
        by_date[session] = record

    if set(by_date) != set(sessions):
        missing = sorted(set(sessions) - set(by_date))
        extra = sorted(set(by_date) - set(sessions))
        return {
            "status": "WAIT_FOR_DATA",
            "reason": f"Bhavcopy session mismatch; missing={len(missing)}, extra={len(extra)}",
        }

    rows = []
    for session in sessions:
        record = by_date[session]
        result = extract_nse_eq_ohlc_row(
            record.get("bhavcopy"),
            symbol=symbol,
            expected_session=session,
            source_url=record.get("source_url", ""),
        )
        if result["status"] != "READY":
            return {"status": result["status"], "reason": f"{session}: {result['reason']}"}
        rows.append(result)

    return {
        "status": "READY",
        "reason": "",
        "Symbol": str(symbol).strip().upper(),
        "ISIN": rows[0]["ISIN"],
        "ohlc": pd.DataFrame(rows),
        "window_start": sessions[0].isoformat(),
        "window_end": sessions[-1].isoformat(),
        "window_sessions": len(rows),
    }
