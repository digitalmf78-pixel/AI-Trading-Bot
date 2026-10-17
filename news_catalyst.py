"""Collect official NSE filings and free news corroboration for V8 top-volume names.

The NSE RSS feeds are the primary source. Google News RSS is used only to find
secondary coverage. A headline is not treated as proof of why a stock moved.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
import os
import re
import xml.etree.ElementTree as ET

import pandas as pd
import requests


NEWS_COLUMNS = [
    "TckrSymb", "PublishedAt", "Headline", "Source", "SourceType",
    "URL", "Impact", "EventID", "SourceDomain",
]
NSE_FEEDS = {
    "NSE company announcements":
        "https://archives.nseindia.com/content/RSS/Online_announcements.xml",
    "NSE financial filings":
        "https://nsearchives.nseindia.com/content/RSS/Integrated_Filing_Financials.xml",
}
EQUITY_MASTER_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
EQUITY_MASTER_CACHE = Path("data") / "bhavcopy" / "EQUITY_L.csv"
GOOGLE_RSS_URL = "https://news.google.com/rss/search"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; NSE-V8-Catalyst-Report/1.0)",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}


def _clean(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", unescape(value or ""))
    return re.sub(r"\s+", " ", value).strip()


def _item_text(item: ET.Element, *field_names: str) -> str:
    """Read requested RSS fields by local XML name, regardless of namespace."""
    wanted = {name.strip().lower() for name in field_names}
    values: list[str] = []
    for node in item.iter():
        local_name = str(node.tag).rsplit("}", 1)[-1].split(":")[-1].strip().lower()
        if local_name in wanted and node.text:
            value = _clean(node.text)
            if value and value not in values:
                values.append(value)
    return " ".join(values)


def _norm(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", _clean(value).upper()).strip()


def _rss_debug_fields(item: ET.Element, max_fields: int = 12, max_value: int = 220) -> dict[str, str]:
    """Return bounded, namespace-safe RSS fields for diagnostics and tests."""
    fields: dict[str, str] = {}
    for node in item.iter():
        key = str(node.tag).rsplit("}", 1)[-1].split(":")[-1].strip().lower()
        if not key or key in fields or node.text is None:
            continue
        value = _clean(node.text)
        if not value:
            continue
        fields[key] = value[:max(1, int(max_value))]
        if len(fields) >= max(1, int(max_fields)):
            break
    return fields


def _published(item: ET.Element) -> datetime | None:
    """Read RSS/RDF/Atom timestamps in RFC 2822 or ISO-8601 form.

    NSE feeds can contain ISO-8601 timestamps and namespace-qualified date
    tags. An RFC-2822-only parser silently discarded those valid entries.
    """
    preferred = {
        "pubdate": 0,
        "date": 1,
        "published": 2,
        "updated": 3,
        "issued": 4,
        "created": 5,
        "modified": 6,
        "filingdate": 7,
        "fileddate": 8,
        "broadcastdatetime": 9,
        "announcementdate": 10,
        "submissiondate": 11,
        "datetime": 12,
        "timestamp": 13,
        "dateandtime": 14,
    }
    values: list[tuple[int, str]] = []
    for node in item.iter():
        local_name = str(node.tag).rsplit("}", 1)[-1].split(":")[-1].strip().lower()
        if local_name in preferred and node.text and node.text.strip():
            values.append((preferred[local_name], node.text.strip()))

    for _, raw in sorted(values, key=lambda entry: entry[0]):
        try:
            stamp = parsedate_to_datetime(raw)
            if stamp is not None:
                if stamp.tzinfo is None:
                    # NSE RSS date strings may be RFC-like but omit a timezone.
                    # Interpret timezone-naive exchange timestamps as India local time,
                    # otherwise an evening IST filing can be shifted past the EOD window.
                    stamp = pd.Timestamp(stamp).tz_localize("Asia/Kolkata").to_pydatetime()
                return stamp.astimezone(timezone.utc)
        except (TypeError, ValueError, OverflowError):
            pass

        try:
            stamp = pd.Timestamp(raw)
            if pd.isna(stamp):
                continue
            if stamp.tzinfo is None:
                # NSE's "16-Oct-2026 21:49:19" style dates have no explicit zone
                # but are India-local exchange timestamps.
                stamp = stamp.tz_localize("Asia/Kolkata")
            stamp = stamp.tz_convert("UTC")
            return stamp.to_pydatetime()
        except (TypeError, ValueError, OverflowError):
            continue
    return None


def _source_domain(url: str) -> str:
    match = re.search(r"https?://([^/]+)", url or "", re.I)
    return (match.group(1).lower().removeprefix("www.") if match else "")


_LEGAL_SUFFIXES = {
    "LIMITED", "LTD", "PRIVATE", "PVT", "COMPANY", "CORPORATION", "CORP",
    "INCORPORATED", "INC", "PLC",
}


def _company_base(value: str) -> str:
    """Normalize a registered issuer name without trailing legal suffixes."""
    tokens = _norm(value).split()
    while tokens and tokens[-1] in _LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def _issuer_match_reason(symbol: str, headline: str, company: str = "") -> str:
    """Match an issuer by its registered name or an explicit market ticker.

    Registered names are matched as complete normalized phrases. Ticker matching
    is deliberately stricter than substring matching: bare common words such as
    TECH or DIVIDEND are not accepted as issuer identifiers.
    """
    symbol = str(symbol or "").strip().upper()
    raw_text = _clean(headline or "")
    title = _norm(raw_text)
    if not symbol or not title:
        return ""

    company_base = _company_base(company)
    company_tokens = company_base.split()
    if company_base:
        distinctive = len(company_base) >= 5 and (
            len(company_tokens) >= 2 or len(company_base) >= 8
        )
        if distinctive and re.search(
            rf"(?<![A-Z0-9]){re.escape(company_base)}(?![A-Z0-9])", title
        ):
            return "COMPANY_NAME_MATCH"

    escaped = re.escape(symbol)
    # Punctuation is removed by _norm, so check explicit ticker forms in raw text.
    raw_explicit_patterns = (
        rf"(?<![A-Z0-9])NSE\s*[:\-]\s*{escaped}(?![A-Z0-9])",
        rf"(?<![A-Z0-9])\(\s*{escaped}\s*\)(?![A-Z0-9])",
        rf"(?<![A-Z0-9]){escaped}\.NS(?![A-Z0-9])",
    )
    if any(re.search(pattern, raw_text, flags=re.IGNORECASE) for pattern in raw_explicit_patterns):
        return "EXPLICIT_TICKER_MATCH"

    normalized_patterns = (
        rf"(?<![A-Z0-9])NSE\s+{escaped}(?![A-Z0-9])",
        rf"(?<![A-Z0-9]){escaped}\s+NS(?![A-Z0-9])",
    )
    if any(re.search(pattern, title) for pattern in normalized_patterns):
        return "EXPLICIT_TICKER_MATCH"
    return ""


def _secondary_search_queries(symbol: str, company: str = "") -> list[str]:
    """Build separate broad-enough Google News queries; strict matching happens later.

    Requiring both an exact company name and ticker in one query was too restrictive:
    many valid articles mention the registered issuer name but omit its NSE symbol.
    The separate ticker query is only for discovery; it never bypasses issuer matching.
    """
    symbol = str(symbol or "").strip().upper()
    company = str(company or "").strip()
    queries: list[str] = []
    if company:
        # Preserve the registered name and legal suffix as it appears in the master.
        queries.append(f'"{company}" when:10d')
    if symbol:
        queries.append(f'"{symbol}" NSE stock when:10d')
    if not queries and symbol:
        queries.append(f'"{symbol}" when:10d')
    return queries



def _filter_catalyst_candidates(candidates: pd.DataFrame) -> pd.DataFrame:
    """Apply the inclusive Delivery >= 60% gate and the required setup gate."""
    filtered = candidates.copy()
    if "AvgDelivery5D" in filtered.columns:
        # Numeric evidence is the source of truth whenever it is present.
        delivery = pd.to_numeric(filtered["AvgDelivery5D"], errors="coerce")
        before = len(filtered)
        filtered = filtered[delivery.ge(60.0)].copy()
        print(
            f"[NEWS-DIAG] Numeric delivery gate: before={before}, after={len(filtered)}, "
            f"removed={before-len(filtered)}, rule=AvgDelivery5D>=60%"
        )
    elif "DeliveryFilterStatus" in filtered.columns:
        statuses = filtered["DeliveryFilterStatus"].astype(str).str.upper().str.strip()
        allowed = {
            "PASS_GE_60_PERCENT",
            "PASS_GT_60_PERCENT",
            "PASS_AT_OR_ABOVE_60_PERCENT",
            "PASS",
        }
        before = len(filtered)
        filtered = filtered[statuses.isin(allowed)].copy()
        print(
            f"[NEWS-DIAG] Delivery gate: before={before}, after={len(filtered)}, "
            f"removed={before-len(filtered)}, rule=AvgDelivery5D>=60%"
        )
    else:
        print("[NEWS-DIAG] Delivery evidence unavailable; assuming caller supplied pre-screened candidates.")

    if "SetupType" in filtered.columns:
        setup = filtered["SetupType"].astype(str).str.upper().str.strip()
        before_setup = len(filtered)
        filtered = filtered[setup.str.contains(r"BREAKOUT|PULLBACK", regex=True, na=False)].copy()
        print(
            f"[NEWS-DIAG] SetupType gate: before={before_setup}, after={len(filtered)}, "
            f"removed={before_setup-len(filtered)}"
        )
    return filtered


def _impact(headline: str) -> str:
    """Classify catalyst impact without treating every management exit as bad news.

    A bare resignation is a management-change event, not sufficient evidence of
    negative impact by itself. Specific auditor resignation and explicit adverse
    financial/regulatory language remain negative signals.
    """
    text = _norm(headline)
    negative = (
        "DEFAULT", "FRAUD", "INSOLVENCY", "BANKRUPTCY", "PENALTY",
        "FINES", "DOWNGRADE", "ORDER CANCELLED", "CONTRACT TERMINATED",
        "PROBE", "INVESTIGATION", "LOSSES WIDEN", "PROFIT FALL",
        "PROFIT DECLINE", "REVENUE FALL", "REVENUE DECLINE",
        "PLEDGE INVOCATION", "AUDITOR RESIGNS", "AUDITOR RESIGNATION",
        "REGULATORY ACTION",
    )
    positive = (
        "RECORD ORDER", "WINS ORDER", "SECURES ORDER", "ORDER WORTH",
        "PROFIT JUMPS", "PROFIT RISE", "PROFIT GROWS", "REVENUE GROWS",
        "REVENUE RISE", "DEBT REDUCTION", "CREDIT RATING UPGRADE",
        "APPROVAL RECEIVED", "BUYBACK", "DIVIDEND INCREASE",
    )
    is_negative = any(term in text for term in negative)
    is_positive = any(term in text for term in positive)
    if is_negative and is_positive:
        return "neutral"
    if is_negative:
        return "negative"
    if is_positive:
        return "positive"
    return "neutral"


def category_marathi(headline: str) -> str:
    text = _norm(headline)
    categories = [
        (("FINANCIAL RESULTS", "QUARTERLY RESULTS", "Q1 RESULTS", "Q2 RESULTS", "Q3 RESULTS", "Q4 RESULTS", "PROFIT", "REVENUE"), "तिमाही आर्थिक निकाल"),
        (("MANAGEMENT", "MANAGING DIRECTOR", "DIRECTOR", "CEO", "CFO", "RESIGNATION", "APPOINTMENT"), "व्यवस्थापन किंवा संचालकांतील बदल"),
        (("ORDER", "CONTRACT", "WORK ORDER", "PROJECT AWARD"), "ऑर्डर किंवा करार"),
        (("FUND RAISING", "FUNDRAISING", "PREFERENTIAL ISSUE", "RIGHTS ISSUE", "QIP", "WARRANTS"), "निधी उभारणी किंवा नवीन समभाग"),
        (("CREDIT RATING", "RATING ACTION", "RATING UPGRADE", "RATING DOWNGRADE"), "पतमानांकनातील बदल"),
        (("SEBI", "REGULATORY", "PENALTY", "FINE", "INVESTIGATION", "FRAUD", "DEFAULT", "INSOLVENCY"), "नियामक किंवा कायदेशीर घडामोड"),
        (("ACQUISITION", "MERGER", "AMALGAMATION", "DIVESTMENT", "SUBSIDIARY"), "खरेदी, विलीनीकरण किंवा व्यवसायातील बदल"),
        (("DIVIDEND", "BUYBACK", "BONUS", "SPLIT"), "लाभांश किंवा समभागांवरील कृती"),
        (("AUDITOR", "AUDIT QUALIFICATION"), "लेखापरीक्षक किंवा लेखापरीक्षणातील बाब"),
        (("INSIDER TRADING", "PROMOTER", "SHAREHOLDING", "ENCUMBRANCE", "PLEDGE"), "प्रवर्तक किंवा समभागधारणेतील बदल"),
        (("BOARD MEETING", "INVESTOR MEET", "ANALYST MEET"), "बैठकीची सूचना; निर्णय अजून स्पष्ट नाही"),
    ]
    for terms, label in categories:
        if any(term in text for term in terms):
            return label
    return "इतर कंपनी घोषणा"


def _read_equity_master() -> dict[str, str]:
    try:
        EQUITY_MASTER_CACHE.parent.mkdir(parents=True, exist_ok=True)
        if not EQUITY_MASTER_CACHE.exists():
            response = requests.get(EQUITY_MASTER_URL, headers=HEADERS, timeout=20)
            response.raise_for_status()
            EQUITY_MASTER_CACHE.write_bytes(response.content)
        master = pd.read_csv(EQUITY_MASTER_CACHE, encoding="utf-8-sig")
        symbol_column = next((c for c in master.columns if c.strip().upper() == "SYMBOL"), None)
        name_column = next((c for c in master.columns if "NAME OF COMPANY" in c.strip().upper()), None)
        if not symbol_column or not name_column:
            return {}
        return {
            str(row[symbol_column]).strip().upper(): str(row[name_column]).strip()
            for _, row in master[[symbol_column, name_column]].dropna().iterrows()
        }
    except Exception as exc:
        print(f"NSE equity master unavailable; will match announcements by symbol: {exc}")
        return {}


class _RSSItemList(list):
    """List of parsed RSS items with a flag for malformed-feed recovery."""

    def __init__(self, items=(), *, partial: bool = False):
        super().__init__(items)
        self.partial = partial


def _rss_items(url: str, params: dict | None = None) -> list[ET.Element]:
    """Fetch RSS items, recovering complete <item> blocks from truncated XML.

    NSE sometimes returns a large RSS payload with a malformed/truncated tail.
    A strict whole-document parse then discards all valid entries. We first try
    the normal XML parser; if it fails, recover only individually well-formed
    complete item blocks. The caller is told the feed was partial, and an
    incomplete item is never fabricated or treated as valid evidence.
    """
    response = requests.get(url, params=params, headers=HEADERS, timeout=15)
    response.raise_for_status()
    payload = response.content
    try:
        root = ET.fromstring(payload)
        items = [
            node for node in root.iter()
            if str(node.tag).rsplit("}", 1)[-1].split(":")[-1].lower() in {"item", "entry"}
        ]
        return _RSSItemList(items, partial=False)
    except ET.ParseError as original_error:
        text = payload.decode(response.encoding or "utf-8", errors="replace")
        fragments = re.findall(r"<item\b[^>]*>.*?</item\s*>", text, flags=re.IGNORECASE | re.DOTALL)
        recovered: list[ET.Element] = []

        # Item fragments can use namespace prefixes declared only on the RSS
        # root. Copy namespace declarations into a temporary wrapper so each
        # complete fragment can be parsed independently.
        root_match = re.search(r"<(?:rss|rdf:RDF|feed)\b([^>]*)>", text, flags=re.IGNORECASE | re.DOTALL)
        root_attrs = root_match.group(1) if root_match else ""
        namespace_attrs = " ".join(re.findall(
            r"\sxmlns(?::[A-Za-z_][\w.-]*)?\s*=\s*(?:\"[^\"]*\"|'[^']*')",
            root_attrs,
            flags=re.IGNORECASE,
        ))
        for fragment in fragments:
            try:
                wrapper = f"<recovery_root{namespace_attrs}>{fragment}</recovery_root>"
                parsed = ET.fromstring(wrapper)
                item = next((node for node in parsed if node.tag.rsplit("}", 1)[-1].lower() == "item"), None)
                if item is not None:
                    recovered.append(item)
            except ET.ParseError:
                # Skip the individual malformed item; do not invent missing data.
                continue

        if not recovered:
            raise original_error
        print(
            f"WARNING: RSS feed parse error for {url}: {original_error}. "
            f"Recovered {len(recovered)} complete item(s); feed marked partial and malformed tail skipped."
        )
        return _RSSItemList(recovered, partial=True)


def _nse_announcement_api_items(symbol: str, from_date, to_date) -> list[ET.Element]:
    """Fetch NSE announcements and log bounded raw-response diagnostics.

    Diagnostics report status, content type, byte count, payload type/count,
    field names and a few non-sensitive record summaries. The function does
    not weaken date cutoffs, infer missing announcements, or bypass access
    controls. An empty response remains empty evidence.
    """
    start = pd.Timestamp(from_date).strftime("%d-%m-%Y")
    end = pd.Timestamp(to_date).strftime("%d-%m-%Y")
    requested_symbol = str(symbol).strip().upper()
    session = requests.Session()
    session.headers.update({**HEADERS, "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements"})
    try:
        landing_url = "https://www.nseindia.com/companies-listing/corporate-filings-announcements"
        landing = session.get(landing_url, timeout=15)
        landing.raise_for_status()
        landing_headers = getattr(landing, "headers", {}) or {}
        landing_content = getattr(landing, "content", b"") or b""
        print(
            f"[NEWS-DIAG] NSE_API_LANDING symbol={requested_symbol} "
            f"status={getattr(landing, 'status_code', 'unknown')} "
            f"content_type={landing_headers.get('Content-Type', 'unknown')!r} "
            f"bytes={len(landing_content)}"
        )

        api_url = "https://www.nseindia.com/api/corporate-announcements"
        params = {"index": "equities", "symbol": requested_symbol, "from_date": start, "to_date": end}
        response = session.get(api_url, params=params, timeout=20)
        response.raise_for_status()
        response_headers = getattr(response, "headers", {}) or {}
        raw_content = getattr(response, "content", b"") or b""
        print(
            f"[NEWS-DIAG] NSE_API_RAW_RESPONSE symbol={requested_symbol} "
            f"status={getattr(response, 'status_code', 'unknown')} "
            f"content_type={response_headers.get('Content-Type', 'unknown')!r} "
            f"bytes={len(raw_content)} range={start}:{end} params={params!r}"
        )

        payload = response.json()
        if isinstance(payload, list):
            raw_count = len(payload)
            dict_records = [record for record in payload if isinstance(record, dict)]
            field_names = sorted({str(key) for record in dict_records for key in record.keys()})
            print(
                f"[NEWS-DIAG] NSE_API_PAYLOAD symbol={requested_symbol} "
                f"payload_type=list raw_records={raw_count} dict_records={len(dict_records)} "
                f"field_names={field_names!r}"
            )
            samples = []
            for record in dict_records[:3]:
                samples.append({
                    "symbol": str(record.get("symbol", ""))[:30],
                    "date": str(record.get("an_dt") or record.get("sort_date") or record.get("dt") or "")[:50],
                    "subject": str(record.get("desc") or record.get("subject") or "")[:120],
                    "seq_id": str(record.get("seq_id") or "")[:40],
                })
            print(f"[NEWS-DIAG] NSE_API_SAMPLE_RECORDS symbol={requested_symbol} samples={samples!r}")
        else:
            print(
                f"[NEWS-DIAG] NSE_API_PAYLOAD symbol={requested_symbol} "
                f"payload_type={type(payload).__name__} raw_records=NA "
                f"field_names=NA"
            )
            return []

        items: list[ET.Element] = []
        symbol_mismatch = 0
        records_without_symbol = 0
        records_without_date = 0
        for record in dict_records:
            record_symbol = str(record.get("symbol", "")).strip().upper()
            # The endpoint is symbol-filtered, but verify every returned row.
            if record_symbol and record_symbol != requested_symbol:
                symbol_mismatch += 1
                continue
            if not record_symbol:
                records_without_symbol += 1
            raw_stamp = record.get("an_dt") or record.get("sort_date") or record.get("dt") or ""
            if not raw_stamp:
                records_without_date += 1
            try:
                parsed_stamp = pd.Timestamp(raw_stamp)
                if not pd.isna(parsed_stamp):
                    # NSE API timestamps are India-local when no offset is present.
                    if parsed_stamp.tzinfo is None:
                        parsed_stamp = parsed_stamp.tz_localize("Asia/Kolkata")
                    raw_stamp = parsed_stamp.isoformat()
            except (TypeError, ValueError, OverflowError):
                pass
            fields = {
                "title": record.get("desc") or record.get("subject") or "",
                "description": record.get("attchmntText") or record.get("desc") or "",
                "pubDate": raw_stamp,
                "link": record.get("attchmntFile") or "",
                "company": record.get("sm_name") or "",
                "symbol": record_symbol,
                "eventid": record.get("seq_id") or "",
            }
            item = ET.Element("item")
            for key, value in fields.items():
                node = ET.SubElement(item, key)
                node.text = str(value or "")
            items.append(item)
        print(
            f"[NEWS-DIAG] NSE_API_NORMALIZE_SUMMARY symbol={requested_symbol} "
            f"raw_records={len(payload)} dict_records={len(dict_records)} "
            f"normalized_items={len(items)} symbol_mismatch={symbol_mismatch} "
            f"records_without_symbol={records_without_symbol} records_without_date={records_without_date}"
        )
        print(f"[NEWS-DIAG] NSE_ANNOUNCEMENT_API_OK symbol={requested_symbol} items={len(items)} range={start}:{end}")
        return items
    except Exception as exc:
        print(f"[NEWS-DIAG] NSE_ANNOUNCEMENT_API_FAIL symbol={requested_symbol} range={start}:{end} error={type(exc).__name__}: {exc}")
        return []


def _news_window_bounds(eod_date, scan_mode=None, now=None):
    """Return the news scan window as UTC bounds plus its IST display bounds.

    EOD mode: five calendar dates inclusive, from 00:00 IST on EOD date - 4
    days through 22:00 IST on the EOD date.

    PREMARKET mode: five calendar dates inclusive relative to the next entry
    session's local scan date, through 09:15 IST on that date. This captures
    overnight/weekend announcements without changing the technical EOD date.
    """
    mode = str(scan_mode or os.getenv("NEWS_SCAN_MODE", "EOD")).strip().upper()
    if mode not in {"EOD", "PREMARKET"}:
        print(f"[NEWS-DIAG] UNKNOWN_SCAN_MODE requested={mode!r}; falling back to EOD")
        mode = "EOD"

    if now is None:
        now_ist = pd.Timestamp.now(tz="Asia/Kolkata")
    else:
        now_ist = pd.Timestamp(now)
        now_ist = now_ist.tz_localize("Asia/Kolkata") if now_ist.tzinfo is None else now_ist.tz_convert("Asia/Kolkata")

    if mode == "PREMARKET":
        end_day = now_ist.normalize()
        start_ist = end_day - pd.Timedelta(days=4)
        end_ist = end_day + pd.Timedelta(hours=9, minutes=15)
    else:
        eod_day = pd.Timestamp(eod_date)
        eod_day = eod_day.tz_localize("Asia/Kolkata") if eod_day.tzinfo is None else eod_day.tz_convert("Asia/Kolkata")
        end_day = eod_day.normalize()
        start_ist = end_day - pd.Timedelta(days=4)
        end_ist = end_day + pd.Timedelta(hours=22)

    return (
        start_ist.tz_convert("UTC").to_pydatetime(),
        end_ist.tz_convert("UTC").to_pydatetime(),
        start_ist,
        end_ist,
        mode,
    )


def collect_catalyst_news(result: pd.DataFrame, eod_date, session_dates=None) -> tuple[pd.DataFrame, dict[str, str]]:
    """Collect NSE filings and secondary news for the candidate rows supplied by the V8 pipeline."""
    if result.empty or "TckrSymb" not in result.columns:
        return pd.DataFrame(columns=NEWS_COLUMNS), {"NSE": "no candidates", "secondary": "not checked"}

    candidates = result.copy()
    candidates["TckrSymb"] = candidates["TckrSymb"].astype(str).str.strip().str.upper()
    candidates = candidates[
        candidates["TckrSymb"].ne("")
        & candidates["TckrSymb"].str.lower().ne("nan")
    ].drop_duplicates(subset=["TckrSymb"]).copy()

    # Enforce delivery and setup gates when upstream evidence is supplied.
    # Delivery is inclusive: exactly 60.00% passes.
    candidates = _filter_catalyst_candidates(candidates)

    if candidates.empty:
        Path("data/inputs").mkdir(parents=True, exist_ok=True)
        empty = pd.DataFrame(columns=NEWS_COLUMNS)
        empty.to_csv("data/inputs/news_evidence_auto.csv", index=False)
        return empty, {"NSE": "no shortlisted candidates", "secondary": "not checked"}

    symbols = set(candidates["TckrSymb"].tolist())
    names = _read_equity_master()
    print(
        "[NEWS-DIAG] ISSUER_MASTER "
        f"candidate_count={len(symbols)} mapped_company_names={sum(bool(str(names.get(sym, '')).strip()) for sym in symbols)} "
        f"candidates={[(sym, names.get(sym, '')) for sym in sorted(symbols)]!r}"
    )
    cutoff, window_end, window_start_ist, window_end_ist, scan_mode = _news_window_bounds(eod_date)
    cutoff_ist_date = window_start_ist.date()
    window_end_ist_date = window_end_ist.date()
    print(
        f"[NEWS-DIAG] NEWS_WINDOW mode={scan_mode} "
        f"start_ist={window_start_ist.strftime('%Y-%m-%d %H:%M:%S %Z')} "
        f"end_ist={window_end_ist.strftime('%Y-%m-%d %H:%M:%S %Z')} "
        f"eod_date={pd.Timestamp(eod_date).date()} "
        f"calendar_days=5"
    )

    rows: list[dict[str, str]] = []
    status = {"NSE": "available", "secondary": "available"}
    nse_successes = 0
    nse_partial = False
    official_window_records = 0

    # Read each exchange feed once, then map company names/symbols to the Top 20.
    for feed_name, feed_url in NSE_FEEDS.items():
        try:
            items = _rss_items(feed_url)
        except Exception as exc:
            print(f"[NEWS-DIAG] OFFICIAL_FEED_FETCH_FAIL feed={feed_name!r} url={feed_url} error={type(exc).__name__}: {exc}")
            continue
        nse_successes += 1
        partial = bool(getattr(items, "partial", False))
        nse_partial = nse_partial or partial
        feed_items = len(items)
        date_valid = 0
        date_rejected = 0
        date_missing = 0
        before_cutoff = 0
        after_window = 0
        issuer_matches = 0
        in_window_samples: list[str] = []
        timestamp_samples: list[str] = []
        print(f"[NEWS-DIAG] OFFICIAL_FEED_FETCH_OK feed={feed_name!r} items={feed_items} partial={partial} url={feed_url}")
        for item in items:
            title = _item_text(item, "title")
            description = _item_text(item, "description", "summary", "content", "abstract")
            issuer_fields = _item_text(item, "company", "companyname", "issuer", "issuername", "symbol", "ticker")
            match_text = " ".join(part for part in (title, description, issuer_fields) if part)
            stamp = _published(item)
            if len(timestamp_samples) < 5:
                timestamp_samples.append(_rss_debug_fields(item, max_fields=16).get("pubdate", "") or
                                         _rss_debug_fields(item, max_fields=16).get("date", "") or
                                         _rss_debug_fields(item, max_fields=16).get("published", "") or
                                         _rss_debug_fields(item, max_fields=16).get("filingdate", "") or
                                         "NO_RECOGNIZED_DATE_FIELD")
            if stamp is None:
                date_missing += 1
                date_rejected += 1
                continue
            if stamp < cutoff:
                before_cutoff += 1
                date_rejected += 1
                continue
            if stamp > window_end:
                after_window += 1
                date_rejected += 1
                continue
            date_valid += 1
            if len(in_window_samples) < 5:
                in_window_samples.append((title or description)[:220])
            link = _clean(item.findtext("link", ""))
            for symbol in symbols:
                company = names.get(symbol, "")
                match_reason = _issuer_match_reason(symbol, match_text, company)
                if not match_reason:
                    continue
                issuer_matches += 1
                print(f"[NEWS-DIAG] OFFICIAL_ISSUER_MATCH feed={feed_name!r} symbol={symbol} reason={match_reason} headline={title[:180]!r}")
                rows.append({
                    "TckrSymb": symbol,
                    "PublishedAt": stamp.isoformat() if stamp else "",
                    "Headline": title or description,
                    "Source": "NSE India",
                    "SourceType": "primary",
                    "URL": link or "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
                    "Impact": _impact(title + " " + description),
                    "EventID": "",
                    "SourceDomain": _source_domain(feed_url) or "archives.nseindia.com",
                })
        print(
            f"[NEWS-DIAG] OFFICIAL_FEED_SUMMARY feed={feed_name!r} items={feed_items} "
            f"date_valid={date_valid} date_missing={date_missing} before_cutoff={before_cutoff} "
            f"after_window={after_window} date_rejected_or_missing={date_rejected} issuer_matches={issuer_matches}"
        )
        official_window_records += date_valid
        if date_valid == 0:
            print(f"[NEWS-DIAG] OFFICIAL_DATE_ZERO_SAMPLES feed={feed_name!r} samples={timestamp_samples!r}")
        if issuer_matches == 0 and in_window_samples:
            print(f"[NEWS-DIAG] OFFICIAL_ZERO_MATCH_SAMPLES feed={feed_name!r} samples={in_window_samples!r}")

    # The public RSS feeds are global and can contain only post-EOD items.
    # If a candidate has no official match from RSS, query NSE's issuer/date-
    # filtered official announcements endpoint for the same permitted window.
    # The official API date parameters must match the same exact IST window used
    # by RSS/secondary filtering (including Monday morning after a weekend).
    api_start_date = cutoff_ist_date
    api_end_date = window_end_ist_date
    primary_symbols_found = {str(row.get("TckrSymb", "")).upper() for row in rows if str(row.get("SourceType", "")).lower() == "primary"}
    for symbol in sorted(symbols - primary_symbols_found):
        api_items = _nse_announcement_api_items(symbol, api_start_date, api_end_date)
        api_matches = 0
        for item in api_items:
            title = _item_text(item, "title")
            description = _item_text(item, "description")
            issuer_fields = _item_text(item, "company", "symbol")
            if _issuer_match_reason(symbol, " ".join((title, description, issuer_fields)), names.get(symbol, "")) == "":
                continue
            stamp = _published(item)
            if stamp is None or stamp < cutoff or stamp > window_end:
                continue
            api_matches += 1
            rows.append({
                "TckrSymb": symbol, "PublishedAt": stamp.isoformat(),
                "Headline": title or description, "Source": "NSE India",
                "SourceType": "primary", "URL": _item_text(item, "link") or "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
                "Impact": _impact(title + " " + description), "EventID": _item_text(item, "eventid"),
                "SourceDomain": "nseindia.com",
            })
        print(f"[NEWS-DIAG] NSE_ANNOUNCEMENT_API_SUMMARY symbol={symbol} matched={api_matches}")

    if nse_successes == 0:
        status["NSE"] = "unavailable"
    elif nse_successes < len(NSE_FEEDS) or nse_partial:
        status["NSE"] = "partly available"

    # Free Google News RSS helps discover independent press coverage. It never
    # upgrades itself to primary evidence; the NSE file remains authoritative.
    secondary_successes = 0
    secondary_partial = False
    for symbol in sorted(symbols):
        company = names.get(symbol, "").strip()
        combined_items: list[ET.Element] = []
        item_keys: set[tuple[str, str]] = set()
        query_success = False
        symbol_partial = False
        for query in _secondary_search_queries(symbol, company):
            try:
                fetched = _rss_items(GOOGLE_RSS_URL, {
                    "q": query, "hl": "en-IN", "gl": "IN", "ceid": "IN:en",
                })
                query_success = True
                symbol_partial = symbol_partial or bool(getattr(fetched, "partial", False))
                print(f"[NEWS-DIAG] SECONDARY_QUERY symbol={symbol} query={query!r} items={len(fetched)}")
                for item in fetched:
                    key = (_item_text(item, "title").casefold(), _item_text(item, "link").casefold())
                    if key not in item_keys:
                        item_keys.add(key)
                        combined_items.append(item)
            except Exception as exc:
                print(f"[NEWS-DIAG] SECONDARY_FEED_FETCH_FAIL symbol={symbol} query={query!r} error={type(exc).__name__}: {exc}")
        if not query_success:
            continue
        secondary_successes += 1
        secondary_partial = secondary_partial or symbol_partial
        secondary_matches = 0
        samples: list[str] = []
        print(f"[NEWS-DIAG] SECONDARY_FEED_FETCH_OK symbol={symbol} items={len(combined_items)} partial={symbol_partial}")
        for item in combined_items:
            title = _item_text(item, "title")
            description = _item_text(item, "description", "summary", "content", "abstract")
            source_node = next((node for node in item.iter() if str(node.tag).rsplit("}", 1)[-1].lower() == "source"), None)
            source_name = _clean(source_node.text if source_node is not None else "Google News")
            source_url = source_node.get("url", "") if source_node is not None else ""
            stamp = _published(item)
            if stamp is None or stamp < cutoff or stamp > window_end:
                continue
            if len(samples) < 5:
                samples.append(title[:180])
            # A separate broad query is not evidence by itself. Require the registered
            # issuer name or an explicit NSE ticker form in the article text.
            match_reason = _issuer_match_reason(symbol, title + " " + description, company)
            if not match_reason:
                continue
            secondary_matches += 1
            print(f"[NEWS-DIAG] SECONDARY_ISSUER_MATCH symbol={symbol} reason={match_reason} headline={title[:180]!r}")
            rows.append({
                "TckrSymb": symbol,
                "PublishedAt": stamp.isoformat() if stamp else "",
                "Headline": title or description,
                "Source": source_name or "बातमी स्रोत",
                "SourceType": "secondary",
                "URL": _item_text(item, "link"),
                "Impact": _impact(title + " " + description),
                "EventID": "",
                "SourceDomain": _source_domain(source_url),
            })
        if secondary_matches == 0 and samples:
            print(f"[NEWS-DIAG] SECONDARY_ZERO_MATCH_SAMPLES symbol={symbol} samples={samples!r}")
        print(f"[NEWS-DIAG] SECONDARY_FEED_SUMMARY symbol={symbol} items={len(combined_items)} issuer_matches={secondary_matches}")

    if secondary_successes == 0:
        status["secondary"] = "unavailable"
    elif secondary_successes < len(symbols) or secondary_partial:
        status["secondary"] = "partly available"

    frame = pd.DataFrame(rows, columns=NEWS_COLUMNS)
    if not frame.empty:
        frame = frame.drop_duplicates(
            subset=["TckrSymb", "Headline", "SourceDomain"], keep="first"
        )
    Path("data/inputs").mkdir(parents=True, exist_ok=True)
    frame.to_csv("data/inputs/news_evidence_auto.csv", index=False)
    official_rows = int((frame["SourceType"].astype(str).str.lower() == "primary").sum()) if not frame.empty else 0
    secondary_rows = int((frame["SourceType"].astype(str).str.lower() == "secondary").sum()) if not frame.empty else 0
    print(f"[NEWS-DIAG] FINAL_SUMMARY candidates={len(symbols)} NSE_feed_status={status['NSE']} secondary_feed_status={status['secondary']} official_rows={official_rows} secondary_rows={secondary_rows} total_rows={len(frame)}")
    print(f"Catalyst scan: {len(frame)} matched filing/news rows across {len(symbols)} top-volume symbols.")

    if scan_mode == "PREMARKET":
        report_rows = []
        for symbol in sorted(symbols):
            matched = frame[frame["TckrSymb"].astype(str).str.upper() == symbol] if not frame.empty else pd.DataFrame(columns=NEWS_COLUMNS)
            official = matched[matched["SourceType"].astype(str).str.lower().isin({"primary", "official", "exchange", "company", "regulator"})] if not matched.empty else pd.DataFrame(columns=NEWS_COLUMNS)
            secondary = matched[~matched.index.isin(official.index)] if not matched.empty else pd.DataFrame(columns=NEWS_COLUMNS)
            if not official.empty:
                news_status = "OFFICIAL_NEWS_FOUND"
                chosen = official.iloc[0]
            elif status.get("NSE") != "available" or official_window_records == 0:
                # Do not claim NO_NEWS_FOUND when the official feeds returned no
                # records in the requested window; coverage cannot be established.
                news_status = "WAIT_FOR_DATA"
                chosen = secondary.iloc[0] if not secondary.empty else None
            elif not secondary.empty:
                news_status = "SECONDARY_ONLY_UNVERIFIED"
                chosen = secondary.iloc[0]
            else:
                news_status = "NO_NEWS_FOUND"
                chosen = None
            report_rows.append({
                "TckrSymb": symbol,
                "EODDate": str(eod_date),
                "ScanMode": scan_mode,
                "WindowStartIST": window_start_ist.strftime("%Y-%m-%d %H:%M:%S %Z"),
                "WindowEndIST": window_end_ist.strftime("%Y-%m-%d %H:%M:%S %Z"),
                "NSEFeedStatus": status.get("NSE", "WAIT_FOR_DATA"),
                "OfficialWindowRecords": official_window_records,
                "NewsStatus": news_status,
                "OfficialRows": len(official),
                "SecondaryRows": len(secondary),
                "Headline": str(chosen.get("Headline", "")) if chosen is not None else "",
                "SourceType": str(chosen.get("SourceType", "")) if chosen is not None else "",
                "PublishedAt": str(chosen.get("PublishedAt", "")) if chosen is not None else "",
                "Source": str(chosen.get("Source", "")) if chosen is not None else "",
                "URL": str(chosen.get("URL", "")) if chosen is not None else "",
            })
        Path("outputs").mkdir(parents=True, exist_ok=True)
        premarket_path = Path("outputs") / "v8_premarket_news_check.csv"
        pd.DataFrame(report_rows).to_csv(premarket_path, index=False)
        print(f"[NEWS-DIAG] PREMARKET_REPORT path={premarket_path} candidates={len(report_rows)} official_window_records={official_window_records} statuses={pd.DataFrame(report_rows)['NewsStatus'].value_counts().to_dict() if report_rows else {}}")
    return frame, status


def _event_impact_marathi(headline: str, impact: str) -> str:
    if impact == "positive":
        return "मथळ्यात सकारात्मक संकेत दिसतो; मूळ कागदपत्र तपासा"
    if impact == "negative":
        return "मथळ्यात नकारात्मक धोका दिसतो; मूळ कागदपत्र तपासा"
    return "मथळ्यावरून परिणाम स्पष्ट नाही; अंदाज बांधलेला नाही"


def _eod_market_close(eod_date) -> pd.Timestamp:
    day = pd.Timestamp(eod_date)
    day = day.tz_localize("Asia/Kolkata") if day.tzinfo is None else day.tz_convert("Asia/Kolkata")
    return day.normalize() + pd.Timedelta(hours=15, minutes=30)


def write_catalyst_top20_report(result: pd.DataFrame, eod_date, news: pd.DataFrame) -> None:
    candidates = result.copy()
    candidates["RVOL"] = pd.to_numeric(candidates.get("RVOL"), errors="coerce")
    candidates = candidates.sort_values("RVOL", ascending=False).head(20)
    report_rows = []
    for _, row in candidates.iterrows():
        symbol = str(row.get("TckrSymb", "")).strip()
        matched = news[news["TckrSymb"].astype(str).str.upper() == symbol.upper()] if not news.empty else pd.DataFrame()
        official = matched[matched["SourceType"].astype(str).str.lower().isin({"primary", "official", "exchange", "company", "regulator"})] if not matched.empty else pd.DataFrame()
        secondary = matched[~matched.index.isin(official.index)] if not matched.empty else pd.DataFrame()
        chosen = official.iloc[0] if not official.empty else secondary.iloc[0] if not secondary.empty else None
        report_rows.append({
            "EODDate": str(eod_date),
            "TckrSymb": symbol,
            "PriceChangePct": row.get("PriceChangePct"),
            "RVOL": row.get("RVOL"),
            "VolumeSignal": row.get("VolumeReason", ""),
            "VolumeSignalSource": "OHLCV pattern only; not confirmed cause",
            "NewsEvidenceStatus": row.get("NewsEvidenceStatus", "NO_DATA"),
            "CatalystCategoryMarathi": category_marathi(str(chosen.get("Headline", ""))) if chosen is not None else "घोषणा सापडली नाही",
            "Headline": str(chosen.get("Headline", "")) if chosen is not None else "",
            "SourceType": str(chosen.get("SourceType", "")) if chosen is not None else "",
            "Source": str(chosen.get("Source", "")) if chosen is not None else "",
            "PublishedAt": str(chosen.get("PublishedAt", "")) if chosen is not None else "",
            "URL": str(chosen.get("URL", "")) if chosen is not None else "",
            "SecondarySourceCount": len(secondary),
        })
    Path("outputs").mkdir(parents=True, exist_ok=True)
    pd.DataFrame(report_rows).to_csv("outputs/v8_catalyst_top20.csv", index=False)


def build_marathi_digest(result: pd.DataFrame, eod_date, news: pd.DataFrame, feed_status: dict[str, str]) -> list[str]:
    """Build a point-wise Marathi/English report for every screened candidate.

    EMA44 proximity is reported but is never used to reject a shortlisted symbol.
    """
    scan_mode = str(os.getenv("NEWS_SCAN_MODE", "EOD")).strip().upper()
    if result.empty:
        heading = "🌅 NSE SWING TRADING V8.0 — PRE-MARKET NEWS CHECK" if scan_mode == "PREMARKET" else "NSE SWING TRADING V8.0 — EOD REPORT"
        return [
            heading,
            f"Latest EOD data date / शेवटचा EOD डेटा: {eod_date}",
            "Premarket mode checks the previous five calendar days through 09:15 IST; this is a news refresh, not an automatic order." if scan_mode == "PREMARKET" else "",
            "आजच्या Pipeline मध्ये पुढील विश्लेषणासाठी पात्र Stock उपलब्ध नाही.",
            "No eligible candidate reached the detailed-analysis stage.",
            "हा निकाल EMA44 proximity मुळे नाही; आधीच्या selection gates चा परिणाम आहे.",
        ]

    candidates = result.copy()
    if "RVOL" in candidates.columns:
        candidates["RVOL"] = pd.to_numeric(candidates["RVOL"], errors="coerce")
        candidates = candidates.sort_values("RVOL", ascending=False, na_position="last").head(20)
    market_close = _eod_market_close(eod_date)

    def val(row, key, digits=2, suffix=""):
        value = pd.to_numeric(pd.Series([row.get(key)]), errors="coerce").iloc[0]
        return f"{value:+.{digits}f}{suffix}" if pd.notna(value) and suffix == "%" else f"{value:.{digits}f}{suffix}" if pd.notna(value) else "NA / उपलब्ध नाही"

    if scan_mode == "PREMARKET":
        _, _, window_start_ist, window_end_ist, _ = _news_window_bounds(eod_date, scan_mode=scan_mode)
        heading = "🌅 NSE SWING TRADING V8.0 — PRE-MARKET NEWS CHECK"
        window_note = f"News window / बातम्यांचा कालावधी: {window_start_ist.strftime('%d-%b %H:%M')} to {window_end_ist.strftime('%d-%b %H:%M')} IST (5 calendar days; ends 09:15 IST)."
        safety_note = "PRE-MARKET NEWS REVIEW ONLY — latest technical data is prior EOD; no automatic order or guaranteed entry."
    else:
        heading = "📊 NSE SWING TRADING V8.0 — EOD REPORT"
        window_note = "News window: previous 5 calendar dates through 22:00 IST on the EOD date."
        safety_note = "Analysis only — no automatic order; अंतिम Status सर्व V8 gates नंतरच."

    lines = [
        heading,
        f"Latest EOD data date / शेवटचा EOD डेटा: {eod_date}",
        window_note,
        f"Detailed candidates / तपासलेले Stocks: {len(candidates)}",
        "Rule: EMA20 कायम; EMA50 च्या जागी EMA44.",
        "महत्त्वाचे: NOT_NEAR_EMA44 हा फक्त माहितीचा Status आहे; यामुळे Shortlisted Stock Reject होत नाही.",
        "NOT_NEAR_EMA44 is informational only and does not reject a shortlisted stock.",
        safety_note,
        "",
    ]
    for number, (_, row) in enumerate(candidates.iterrows(), start=1):
        symbol = str(row.get("TckrSymb", "UNKNOWN")).strip().upper()
        lines.append(f"━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"{number}. 📌 {symbol}")
        lines.append(f"1) Price / भाव: Close ₹{val(row, 'ClsPric')} | 1D Change {val(row, 'PriceChangePct', 2, '%')} | 5D Change {val(row, 'PriceChange5D', 2, '%')}")
        lines.append(f"2) Volume: Today {val(row, 'TtlTradgVol', 0)} | 20D Avg {val(row, 'AvgVolume20D', 0)} | RVOL {val(row, 'RVOL')}x")

        delivery_cols = [c for c in candidates.columns if str(c).startswith("Delivery_")]
        delivery_cols = sorted(delivery_cols, key=lambda c: str(c).replace("Delivery_", ""), reverse=True)[:5]
        if delivery_cols:
            day_values = []
            for column in delivery_cols:
                day = str(column).replace("Delivery_", "")
                day_value = pd.to_numeric(pd.Series([row.get(column)]), errors="coerce").iloc[0]
                day_values.append(f"{day}: {day_value:.2f}%" if pd.notna(day_value) else f"{day}: NA")
            lines.append("3) 5-Day Delivery / पाच दिवसांचा Delivery %: " + " | ".join(day_values))
        else:
            lines.append("3) 5-Day Delivery / पाच दिवसांचा Delivery %: Daily values unavailable / रोजचा डेटा उपलब्ध नाही")
        avg_delivery = pd.to_numeric(pd.Series([row.get("AvgDelivery5D")]), errors="coerce").iloc[0]
        avg_delivery_text = f"{avg_delivery:.2f}%" if pd.notna(avg_delivery) else "NA / उपलब्ध नाही"
        lines.append(f"   Average Delivery: {avg_delivery_text} | Filter: {row.get('DeliveryFilterStatus', row.get('DeliveryStatus', 'WAIT_FOR_DATA'))}")

        lines.append(f"4) EMA: EMA20 ₹{val(row, 'EMA20')} | EMA44 ₹{val(row, 'EMA44')} | Distance {val(row, 'EMA44DistancePct', 2, '%')} | EMA44 Trend {row.get('EMA44Trend', 'WAIT_FOR_DATA')}")
        lines.append(f"   Position: {row.get('EMA44Position', 'WAIT_FOR_DATA')} | Proximity: {row.get('EMA44ProximityStatus', 'WAIT_FOR_DATA')} | EMA44 Signal: {row.get('EMA44SignalStatus', 'WAIT_FOR_DATA')}")
        lines.append("   EMA44 note: NOT_NEAR_EMA44 = informational only; shortlisted candidate remains in analysis.")

        lines.append(f"5) Technical: RSI14 {val(row, 'RSI14', 1)} | ADX14 {val(row, 'ADX14', 1)} | Trend {row.get('TrendClassification', 'WAIT_FOR_DATA')}")
        lines.append(f"   Price/Volume: {row.get('PriceVolumeRelationship', 'WAIT_FOR_DATA')} | CLV {val(row, 'CLV')} | Breakout {row.get('BreakoutStatus', 'WAIT_FOR_DATA')} | Pullback {row.get('PullbackStatus', 'WAIT_FOR_DATA')}")
        lines.append(f"6) Support/Resistance: Support ₹{val(row, 'SRSupport')} | Resistance ₹{val(row, 'SRResistance')} | Breakout Level ₹{val(row, 'BreakoutLevel')}")
        lines.append(f"7) Sector/Market: Sector {row.get('Sector', 'Unknown')} | Sector status {row.get('SectorStrengthStatus', 'WAIT_FOR_DATA')} | Market regime {row.get('MarketRegime', 'WAIT_FOR_DATA')}")

        matched = news[news["TckrSymb"].astype(str).str.upper() == symbol] if news is not None and not news.empty and "TckrSymb" in news.columns else pd.DataFrame()
        official = matched[matched["SourceType"].astype(str).str.lower().isin({"primary", "official", "exchange", "company", "regulator", "company_verified", "issuer_verified"})] if not matched.empty and "SourceType" in matched.columns else pd.DataFrame()
        secondary = matched[~matched.index.isin(official.index)] if not matched.empty else pd.DataFrame()
        chosen = official.iloc[0] if not official.empty else secondary.iloc[0] if not secondary.empty else None
        if chosen is None:
            lines.append(f"8) News/Catalyst: {row.get('NewsEvidenceStatus', 'NO_DATA')} — verified matching filing/news not available / पडताळलेली बातमी उपलब्ध नाही.")
        else:
            headline = str(chosen.get("Headline", ""))
            source_type = str(chosen.get("SourceType", "")).lower()
            verification = "Official/primary source" if source_type in {"primary", "official", "exchange", "company", "regulator", "company_verified", "issuer_verified"} else "Secondary source — official confirmation not established"
            lines.append(f"8) News/Catalyst: {headline}")
            lines.append(f"   Source: {chosen.get('Source', 'Unknown')} | {verification} | Impact label: {chosen.get('Impact', 'neutral')}")
            published = pd.to_datetime(chosen.get("PublishedAt", ""), errors="coerce", utc=True)
            if pd.notna(published) and published.tz_convert("Asia/Kolkata") > market_close:
                lines.append("   Timing note: published after EOD close; not confirmed as the cause of today's move.")
            lines.append(f"   Source URL: {chosen.get('URL', '')}")

        lines.append(f"9) Confirmation: 3+1 {row.get('MandatoryConfirmationStatus', 'WAIT_FOR_DATA')} | Evidence categories {row.get('IndependentConfirmationCategories', 'NA')} | Primary source verified {row.get('NewsPrimarySourceVerified', 'WAIT_FOR_DATA')}")
        lines.append(f"10) Risk/Reward: V8 Score {val(row, 'V8Score', 0)}/100 | Entry ₹{val(row, 'EntryPricePlan')} | Stop ₹{val(row, 'StopLossPlan')} | Target 1 ₹{(val(row, 'Target1PricePlan') if pd.notna(pd.to_numeric(pd.Series([row.get('Target1PricePlan')]), errors='coerce').iloc[0]) else val(row, 'TargetPricePlan'))} | Target 2 ₹{val(row, 'Target2PricePlan')} | Risk ₹{val(row, 'RiskAmount')} | Reward ₹{val(row, 'RewardAmount')} | R:R {val(row, 'RiskReward')} ({row.get('RiskRewardStatus', 'WAIT_FOR_DATA')}) | Chase {row.get('ChaseStatus', 'WAIT_FOR_DATA')}")
        lines.append(f"FINAL V8 STATUS: {row.get('EODWatchlistStatus', 'WAIT_FOR_DATA')} | Layer status: {row.get('EODLayerStatus', 'WAIT_FOR_DATA')}")
        lines.append(f"Reason: {row.get('CandidateScreenReasons', row.get('EODLayerReason', 'Check detailed CSV for layer-specific reasons'))}")
        lines.append("")

    lines.append("Data rule: missing/invalid values stay NA or WAIT_FOR_DATA; no values are guessed.")
    lines.append("Source status — NSE: " + str(feed_status.get("NSE", "not checked")) + " | Secondary news: " + str(feed_status.get("secondary", "not checked")))
    lines.append("Disclaimer: research shortlist only, not a guaranteed signal or automatic order.")
    return lines

def send_marathi_telegram(result: pd.DataFrame, eod_date, news: pd.DataFrame, feed_status: dict[str, str], token: str | None, chat_id: str | None) -> None:
    if not token or not chat_id:
        print("Telegram secrets are not configured; Marathi digest was not sent.")
        return
    lines = build_marathi_digest(result, eod_date, news, feed_status)
    chunks: list[str] = []
    current = ""
    for line in lines:
        addition = line + "\n"
        if current and len(current) + len(addition) > 3500:
            chunks.append(current.rstrip())
            current = ""
        current += addition
    if current:
        chunks.append(current.rstrip())
    for index, chunk in enumerate(chunks, start=1):
        text = f"भाग {index}/{len(chunks)}\n{chunk}" if len(chunks) > 1 else chunk
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            timeout=20,
        )
        print(f"Marathi Telegram digest part {index}/{len(chunks)}: HTTP {response.status_code}")
        response.raise_for_status()
