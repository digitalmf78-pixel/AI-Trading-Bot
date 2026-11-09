"""Fetch and validate the official NSE market-wide FII/FPI and DII cash flows.

This feed is aggregate market activity across exchanges. It is not per-stock
institutional buying, and NSE describes the figures as provisional.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

import pandas as pd
import requests

NSE_PAGE_URL = "https://www.nseindia.com/reports/fii-dii"
NSE_API_URL = "https://www.nseindia.com/api/fiidiiTradeReact"
OUTPUT_PATH = Path("outputs") / "v8_fii_dii_market_activity.csv"
DATA_SCOPE = "MARKET_WIDE_AGGREGATE_NOT_PER_STOCK"

REPORT_COLUMNS = [
    "RequestedEODDate", "DataDate", "DataStatus", "DataScope",
    "FiiFpiBuyINRCrore", "FiiFpiSellINRCrore", "FiiFpiNetINRCrore",
    "DiiBuyINRCrore", "DiiSellINRCrore", "DiiNetINRCrore",
    "MarketFlowInterpretation", "NetValueCheck", "SourceURL", "APIURL", "Reason",
]


def _date(value) -> pd.Timestamp:
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()):
        return pd.to_datetime(value, format="%Y-%m-%d", errors="coerce").normalize()
    return pd.to_datetime(value, errors="coerce", dayfirst=True).normalize()


def _number(value) -> float | None:
    try:
        parsed = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _empty_record(eod_date, status="WAIT_FOR_DATA", reason="Official NSE flow data unavailable") -> dict:
    return {
        "RequestedEODDate": pd.to_datetime(eod_date, errors="coerce").date().isoformat()
        if pd.notna(pd.to_datetime(eod_date, errors="coerce")) else "",
        "DataDate": "", "DataStatus": status, "DataScope": DATA_SCOPE,
        "FiiFpiBuyINRCrore": None, "FiiFpiSellINRCrore": None, "FiiFpiNetINRCrore": None,
        "DiiBuyINRCrore": None, "DiiSellINRCrore": None, "DiiNetINRCrore": None,
        "MarketFlowInterpretation": "WAIT_FOR_DATA", "NetValueCheck": "NOT_CHECKED",
        "SourceURL": NSE_PAGE_URL, "APIURL": NSE_API_URL, "Reason": str(reason),
    }


def parse_activity_rows(rows, eod_date) -> dict:
    """Validate the two categories, arithmetic, and exact EOD date."""
    result = _empty_record(eod_date)
    expected = _date(eod_date)
    if pd.isna(expected) or not isinstance(rows, list):
        result["DataStatus"] = "WAIT_FOR_DATA_INVALID_DATE_OR_PAYLOAD"
        result["Reason"] = "EOD date or NSE payload is invalid"
        return result

    categories = {}
    dates = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        category = str(row.get("category", "")).strip().upper()
        if category in {"FII/FPI", "FII", "FPI"}:
            key = "fii"
        elif category == "DII":
            key = "dii"
        else:
            continue
        if key in categories:
            result["DataStatus"] = "WAIT_FOR_DATA_DUPLICATE_CATEGORY"
            result["Reason"] = f"Duplicate NSE category row: {category}"
            return result
        row_date = _date(row.get("date"))
        if pd.isna(row_date):
            result["DataStatus"] = "WAIT_FOR_DATA_INVALID_SOURCE_DATE"
            result["Reason"] = f"NSE {category} row has an invalid date"
            return result
        dates.add(row_date)
        values = {name: _number(row.get(key_name)) for name, key_name in (
            ("buy", "buyValue"), ("sell", "sellValue"), ("net", "netValue")
        )}
        if any(value is None for value in values.values()) or values["buy"] < 0 or values["sell"] < 0:
            result["DataStatus"] = "WAIT_FOR_DATA_INVALID_SOURCE_VALUE"
            result["Reason"] = f"NSE {category} row has missing or invalid rupee values"
            return result
        if abs((values["buy"] - values["sell"]) - values["net"]) > 0.02:
            result["DataStatus"] = "WAIT_FOR_DATA_NET_VALUE_MISMATCH"
            result["NetValueCheck"] = "FAIL"
            result["Reason"] = f"NSE {category} net does not reconcile to buy minus sell"
            return result
        categories[key] = values

    if set(categories) != {"fii", "dii"} or len(dates) != 1:
        result["DataStatus"] = "WAIT_FOR_DATA_INCOMPLETE_CATEGORIES"
        result["Reason"] = "NSE payload must contain one same-date FII/FPI row and one DII row"
        return result

    data_date = next(iter(dates))
    result["DataDate"] = data_date.date().isoformat()
    result["FiiFpiBuyINRCrore"] = categories["fii"]["buy"]
    result["FiiFpiSellINRCrore"] = categories["fii"]["sell"]
    result["FiiFpiNetINRCrore"] = categories["fii"]["net"]
    result["DiiBuyINRCrore"] = categories["dii"]["buy"]
    result["DiiSellINRCrore"] = categories["dii"]["sell"]
    result["DiiNetINRCrore"] = categories["dii"]["net"]
    result["NetValueCheck"] = "PASS"
    if data_date != expected:
        result["DataStatus"] = "WAIT_FOR_DATA_DATE_MISMATCH"
        result["Reason"] = "Latest NSE market-wide flow date does not match the requested EOD date"
        return result

    fii_net, dii_net = result["FiiFpiNetINRCrore"], result["DiiNetINRCrore"]
    if fii_net > 0 and dii_net > 0:
        interpretation = "FII_FPI_AND_DII_NET_BUYING"
    elif fii_net < 0 and dii_net < 0:
        interpretation = "FII_FPI_AND_DII_NET_SELLING"
    elif fii_net > 0 > dii_net:
        interpretation = "FII_FPI_BUYING_DII_SELLING"
    elif dii_net > 0 > fii_net:
        interpretation = "DII_BUYING_FII_FPI_SELLING"
    else:
        interpretation = "MIXED_OR_FLAT"
    result["DataStatus"] = "OFFICIAL_PROVISIONAL_EXACT_DATE"
    result["MarketFlowInterpretation"] = interpretation
    result["Reason"] = "Exact-date NSE aggregate reconciled; provisional market-wide context only"
    return result


def fetch_market_activity(eod_date, session=None, timeout=20) -> dict:
    """Read the NSE report page for cookies, then fetch its official JSON feed."""
    client = session or requests.Session()
    client.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; NSE-V8-FII-DII-Audit/1.0)",
        "Accept": "application/json,text/plain,*/*",
        "Referer": NSE_PAGE_URL,
    })
    try:
        page = client.get(NSE_PAGE_URL, timeout=timeout)
        page.raise_for_status()
        response = client.get(NSE_API_URL, timeout=timeout)
        response.raise_for_status()
        return parse_activity_rows(response.json(), eod_date)
    except Exception as exc:
        return _empty_record(
            eod_date, "WAIT_FOR_DATA_FETCH_ERROR", f"NSE FII/DII fetch failed: {type(exc).__name__}: {exc}"
        )
    finally:
        if session is None:
            client.close()


def write_market_activity(eod_date, record: dict | None = None,
                          output_path: str | Path = OUTPUT_PATH) -> dict:
    """Always write a one-row report, including explicit unavailable status."""
    record = record or fetch_market_activity(eod_date)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{column: record.get(column) for column in REPORT_COLUMNS}]).to_csv(output_path, index=False)
    print(
        f"[FII/DII] requested_eod={record.get('RequestedEODDate', '')} "
        f"data_date={record.get('DataDate', '')} status={record.get('DataStatus')} "
        f"reason={record.get('Reason', '')} scope={DATA_SCOPE} report={output_path}"
    )
    return record


def attach_market_context(frame: pd.DataFrame, record: dict) -> pd.DataFrame:
    """Add market-wide fields for context only; no stock score or gate uses them."""
    output = frame.copy()
    for column in REPORT_COLUMNS:
        if column not in {"SourceURL", "APIURL", "Reason", "RequestedEODDate"}:
            output[f"FiiDii{column}"] = record.get(column)
    output["FiiDiiScope"] = DATA_SCOPE
    return output

