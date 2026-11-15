"""ECMS-only informational enrichment from public NSE disclosures.

Nothing in this module changes the fundamental decision gate.
"""
from __future__ import annotations

from datetime import date, timedelta
from io import StringIO
import json
import re

import pandas as pd
import requests

from strategies.ecms.eod import HEADERS

NSE_EVENT_CALENDAR_URL = "https://www.nseindia.com/api/event-calendar"
NSE_DEALS_URL = "https://www.nseindia.com/api/historicalOR/bulk-block-short-deals"
NSE_EVENT_PAGE = "https://www.nseindia.com/companies-listing/corporate-filings-event-calendar"
NSE_DEALS_PAGE = "https://www.nseindia.com/report-detail/display-bulk-and-block-deals"
EVENT_LOOKAHEAD_DAYS = 30
DEAL_LOOKBACK_DAYS = 30


def _norm(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _pick(row, *names):
    mapped = {_norm(key): value for key, value in row.items()}
    for name in names:
        value = mapped.get(_norm(name))
        if value is not None and str(value).strip() not in {"", "nan", "None", "-"}:
            return value
    return ""


def _payload_rows(response):
    """Accept JSON data arrays or the official CSV response."""
    try:
        payload = response.json()
    except (ValueError, json.JSONDecodeError):
        payload = None
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "records", "result"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    text = str(getattr(response, "text", "") or "").strip()
    if not text or text.startswith("<"):
        raise ValueError("NSE response was empty or HTML, not a data payload")
    frame = pd.read_csv(StringIO(text))
    return frame.to_dict("records")


def _nse_session(session=None, landing_url=NSE_EVENT_PAGE):
    client = session or requests.Session()
    client.headers.update(HEADERS)
    landing = client.get(landing_url, timeout=(5, 12))
    landing.raise_for_status()
    return client


def _as_date(value):
    stamp = pd.to_datetime(value, errors="coerce", dayfirst=True)
    if pd.isna(stamp):
        return None
    if stamp.tzinfo is not None:
        return stamp.tz_convert("Asia/Kolkata").date()
    return stamp.date()


def collect_upcoming_events(symbols, as_of_date: date, lookahead_days=EVENT_LOOKAHEAD_DAYS,
                            session=None):
    """Return confirmed NSE event-calendar rows and per-symbol status."""
    symbols = sorted({str(item).strip().upper() for item in symbols if str(item).strip()})
    end_date = as_of_date + timedelta(days=int(lookahead_days))
    rows, audit = [], []
    try:
        client = _nse_session(session, NSE_EVENT_PAGE)
        response = client.get(
            NSE_EVENT_CALENDAR_URL,
            params={
                "index": "equities",
                "from_date": as_of_date.strftime("%d-%m-%Y"),
                "to_date": end_date.strftime("%d-%m-%Y"),
            },
            timeout=(5, 20),
        )
        response.raise_for_status()
        raw_rows = _payload_rows(response)
        if any(not isinstance(item, dict) for item in raw_rows):
            raise ValueError("NSE event calendar contains non-object rows")
        for item in raw_rows:
            symbol = str(_pick(item, "symbol", "SYMBOL", "tradingSymbol")).strip().upper()
            if symbol not in symbols:
                continue
            event_date = _as_date(_pick(item, "date", "eventDate", "meetingDate", "meeting_date"))
            if event_date is None or not as_of_date <= event_date <= end_date:
                continue
            purpose = str(_pick(item, "purpose", "Purpose", "eventType", "category")).strip()
            details = str(_pick(item, "details", "Details", "description", "subject")).strip()
            rows.append({
                "TckrSymb": symbol,
                "EventDate": event_date.isoformat(),
                "EventType": purpose or "COMPANY_EVENT",
                "EventDetails": details,
                "Source": "NSE Event Calendar",
                "SourceType": "OFFICIAL",
                "SourceURL": NSE_EVENT_PAGE,
                "IsResultEvent": bool(re.search(r"financial\s*results?|quarterly\s*results?", purpose + " " + details, re.I)),
            })
        events = pd.DataFrame(rows, columns=[
            "TckrSymb", "EventDate", "EventType", "EventDetails",
            "Source", "SourceType", "SourceURL", "IsResultEvent",
        ])
        for symbol in symbols:
            symbol_rows = events[events["TckrSymb"].eq(symbol)] if not events.empty else pd.DataFrame()
            result_rows = symbol_rows[symbol_rows["IsResultEvent"].astype(bool)] if not symbol_rows.empty else pd.DataFrame()
            audit.append({
                "TckrSymb": symbol,
                "UpcomingEventsStatus": "AVAILABLE" if not symbol_rows.empty else "NO_CONFIRMED_UPCOMING_EVENTS",
                "UpcomingEvents": " | ".join(
                    f"{r.EventDate}: {r.EventType}" for r in symbol_rows.itertuples()
                ),
                "NextResultDate": result_rows.iloc[0]["EventDate"] if not result_rows.empty else "NOT ANNOUNCED",
                "NextResultDetails": result_rows.iloc[0]["EventDetails"] if not result_rows.empty else "",
                "EventCalendarSourceURL": NSE_EVENT_PAGE,
            })
        return events, pd.DataFrame(audit)
    except Exception as exc:
        audit = [{
            "TckrSymb": symbol,
            "UpcomingEventsStatus": f"WAIT_FOR_DATA:{type(exc).__name__}",
            "UpcomingEvents": "NOT AVAILABLE",
            "NextResultDate": "NOT AVAILABLE",
            "NextResultDetails": "",
            "EventCalendarSourceURL": NSE_EVENT_PAGE,
        } for symbol in symbols]
        return pd.DataFrame(columns=[
            "TckrSymb", "EventDate", "EventType", "EventDetails",
            "Source", "SourceType", "SourceURL", "IsResultEvent",
        ]), pd.DataFrame(audit)


def collect_bulk_block_deals(symbols, as_of_date: date, lookback_days=DEAL_LOOKBACK_DAYS,
                             session=None):
    """Return NSE-disclosed bulk/block deal sides without inventing counterparties."""
    symbols = sorted({str(item).strip().upper() for item in symbols if str(item).strip()})
    start_date = as_of_date - timedelta(days=int(lookback_days) - 1)
    deals, type_status = [], {}
    client = None
    for deal_type in ("bulk_deals", "block_deals"):
        try:
            if client is None:
                client = _nse_session(session, NSE_DEALS_PAGE)
            response = client.get(
                NSE_DEALS_URL,
                params={
                    "optionType": deal_type,
                    "from": start_date.strftime("%d-%m-%Y"),
                    "to": as_of_date.strftime("%d-%m-%Y"),
                    "csv": "true",
                },
                timeout=(5, 25),
            )
            response.raise_for_status()
            raw_rows = _payload_rows(response)
            type_status[deal_type] = "AVAILABLE"
            for item in raw_rows:
                if not isinstance(item, dict):
                    continue
                symbol = str(_pick(item, "symbol", "SYMBOL", "tradingSymbol")).strip().upper()
                if symbol not in symbols:
                    continue
                deal_date = _as_date(_pick(item, "date", "tradeDate", "dealDate"))
                if deal_date is None or not start_date <= deal_date <= as_of_date:
                    continue
                side = str(_pick(item, "buySell", "buy/sell", "side", "buySellIndicator")).strip().upper()
                client_name = str(_pick(item, "clientName", "client name", "client")).strip()
                quantity = _pick(item, "quantityTraded", "quantity traded", "quantity", "qty")
                price = _pick(item, "tradePrice", "trade price", "trade price / wght. avg. price", "trade price / weighted average price", "weighted average price", "price")
                remarks = str(_pick(item, "remarks", "remark")).strip()
                deals.append({
                    "TckrSymb": symbol,
                    "DealDate": deal_date.isoformat(),
                    "DealType": "BULK" if deal_type == "bulk_deals" else "BLOCK",
                    "ClientName": client_name,
                    "Side": side,
                    "Quantity": quantity,
                    "PriceINR": price,
                    "Remarks": remarks,
                    "Source": "NSE",
                    "SourceType": "OFFICIAL",
                    "SourceURL": NSE_DEALS_PAGE,
                })
        except Exception as exc:
            type_status[deal_type] = f"WAIT_FOR_DATA:{type(exc).__name__}"

    deal_frame = pd.DataFrame(deals, columns=[
        "TckrSymb", "DealDate", "DealType", "ClientName", "Side",
        "Quantity", "PriceINR", "Remarks", "Source", "SourceType", "SourceURL",
    ])
    audit = []
    for symbol in symbols:
        symbol_rows = deal_frame[deal_frame["TckrSymb"].eq(symbol)] if not deal_frame.empty else pd.DataFrame()
        bulk = symbol_rows[symbol_rows["DealType"].eq("BULK")] if not symbol_rows.empty else pd.DataFrame()
        block = symbol_rows[symbol_rows["DealType"].eq("BLOCK")] if not symbol_rows.empty else pd.DataFrame()
        if len(symbol_rows) and all(value == "AVAILABLE" for value in type_status.values()) and len(type_status) == 2:
            status = "AVAILABLE"
        elif len(symbol_rows):
            status = "PARTIAL_DATA"
        elif all(value == "AVAILABLE" for value in type_status.values()) and len(type_status) == 2:
            status = "NO_DISCLOSED_DEALS_IN_LOOKBACK"
        elif any(value == "AVAILABLE" for value in type_status.values()):
            status = "PARTIAL_DATA"
        else:
            status = "WAIT_FOR_DATA"
        audit.append({
            "TckrSymb": symbol,
            "BulkBlockDealStatus": status,
            "BulkDealCount": int(len(bulk)),
            "BlockDealCount": int(len(block)),
            "BulkBuyers": " | ".join(sorted(set(bulk.loc[bulk["Side"].str.contains("BUY|B", regex=True), "ClientName"].astype(str)))) if not bulk.empty else "",
            "BulkSellers": " | ".join(sorted(set(bulk.loc[bulk["Side"].str.contains("SELL|S", regex=True), "ClientName"].astype(str)))) if not bulk.empty else "",
            "BlockBuyers": " | ".join(sorted(set(block.loc[block["Side"].str.contains("BUY|B", regex=True), "ClientName"].astype(str)))) if not block.empty else "",
            "BlockSellers": " | ".join(sorted(set(block.loc[block["Side"].str.contains("SELL|S", regex=True), "ClientName"].astype(str)))) if not block.empty else "",
            "BulkBlockDealSummary": " | ".join(
                f"{r.DealType} {r.DealDate} {r.Side} {r.ClientName} qty={r.Quantity} price={r.PriceINR}"
                for r in symbol_rows.itertuples()
            ),
            "BulkBlockLookbackStart": start_date.isoformat(),
            "BulkBlockLookbackEnd": as_of_date.isoformat(),
            "BulkBlockSourceURL": NSE_DEALS_PAGE,
        })
    return deal_frame, pd.DataFrame(audit)


def _number(value):
    try:
        number = float(str(value).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None
    return number if pd.notna(number) else None


def attach_valuation(frame):
    """Add a transparent indicative valuation label; never use it as a gate."""
    result = frame.copy()
    labels, bases = [], []
    for _, row in result.iterrows():
        source = str(row.get("ValuationSource", "") or "").strip()
        as_of = _as_date(row.get("ValuationAsOfDate"))
        sector = str(row.get("ProviderSector", "") or "").lower()
        if not source or as_of is None:
            labels.append("NOT AVAILABLE")
            bases.append("SOURCE_OR_AS_OF_DATE_MISSING")
            continue
        pe = _number(row.get("TrailingPE"))
        peg = _number(row.get("PEG"))
        pb = _number(row.get("PriceToBook"))
        ev_ebitda = _number(row.get("EnterpriseToEBITDA"))
        if any(term in sector for term in ("bank", "nbfc", "insurance", "insurer", "financial")):
            if pb is None or pb <= 0:
                labels.append("NOT AVAILABLE")
                bases.append("FINANCIAL_SECTOR_PB_MISSING")
            else:
                labels.append("CHEAP" if pb <= 1.5 else "EXPENSIVE" if pb >= 3.0 else "FAIR")
                bases.append("P_B_INDICATIVE_BANDS")
        elif pe is not None and pe > 0 and peg is not None and peg > 0:
            labels.append("CHEAP" if pe <= 20 and peg <= 1 else "EXPENSIVE" if pe >= 35 or peg >= 2.5 else "FAIR")
            bases.append("TRAILING_PE_AND_PEG_INDICATIVE_BANDS")
        elif pe is not None and pe > 0 and ev_ebitda is not None and ev_ebitda > 0:
            labels.append("CHEAP" if pe <= 15 and ev_ebitda <= 8 else "EXPENSIVE" if pe >= 35 or ev_ebitda >= 18 else "FAIR")
            bases.append("TRAILING_PE_AND_EV_EBITDA_INDICATIVE_BANDS")
        elif pe is not None and pe > 0:
            labels.append("CHEAP" if pe <= 15 else "EXPENSIVE" if pe >= 35 else "FAIR")
            bases.append("TRAILING_PE_INDICATIVE_BANDS")
        else:
            labels.append("NOT AVAILABLE")
            bases.append("INSUFFICIENT_COMPARABLE_MULTIPLES")
    result["ValuationLabel"] = labels
    result["ValuationBasis"] = bases
    return result
