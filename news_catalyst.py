"""Collect official NSE filings and free news corroboration for V8 top-volume names.

The NSE RSS feeds are the primary source. Google News RSS is used only to find
secondary coverage. A headline is not treated as proof of why a stock moved.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import local
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
import os
import re
import xml.etree.ElementTree as ET

import pandas as pd
import requests
from telegram_research_digest import build_telegram_research_sections


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
# Single-token registered issuer names can be distinctive (e.g. MARICO), but
# generic words must never become issuer evidence by themselves.
_GENERIC_SINGLE_WORD_ISSUER_NAMES = {
    "TECH", "TECHNOLOGY", "TECHNOLOGIES", "INDIA", "INDIAN", "BANK",
    "POWER", "GOLD", "SILVER", "FINANCE", "FINANCIAL", "CAPITAL",
    "INFRA", "INFRASTRUCTURE", "INDUSTRIES", "INDUSTRIAL", "SERVICES",
    "SERVICE", "GLOBAL", "ENTERPRISES", "ENTERPRISE", "TRADING",
    "CHEMICALS", "PHARMA", "HEALTHCARE", "HOSPITALS", "HOSPITAL",
    "REALTY", "TEXTILES", "AGRO", "MOTORS", "MOTOR", "MEDIA",
    "CONSUMER", "CONSTRUCTION", "LOGISTICS", "TRANSPORT", "HOLDINGS",
}


def _company_base(value: str) -> str:
    """Normalize a registered issuer name without trailing legal suffixes."""
    tokens = _norm(value).split()
    while tokens and tokens[-1] in _LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def _prepare_issuer_matcher(symbol: str, company: str = "") -> tuple:
    """Compile immutable issuer patterns once instead of rebuilding them per RSS item."""
    symbol = str(symbol or "").strip().upper()
    company_base = _company_base(company)
    company_tokens = company_base.split()
    distinctive = bool(company_base) and (
        (len(company_tokens) >= 2 and len(company_base) >= 5)
        or (len(company_tokens) == 1 and len(company_base) >= 6
            and company_base not in _GENERIC_SINGLE_WORD_ISSUER_NAMES)
    )
    company_pattern = (
        re.compile(rf"(?<![A-Z0-9]){re.escape(company_base)}(?![A-Z0-9])")
        if distinctive else None
    )
    escaped = re.escape(symbol)
    raw_patterns = tuple(re.compile(pattern, flags=re.IGNORECASE) for pattern in (
        rf"(?<![A-Z0-9])NSE\s*[:\-]\s*{escaped}(?![A-Z0-9])",
        rf"(?<![A-Z0-9])\(\s*{escaped}\s*\)(?![A-Z0-9])",
        rf"(?<![A-Z0-9]){escaped}\.NS(?![A-Z0-9])",
    ))
    normalized_patterns = tuple(re.compile(pattern) for pattern in (
        rf"(?<![A-Z0-9])NSE\s+{escaped}(?![A-Z0-9])",
        rf"(?<![A-Z0-9]){escaped}\s+NS(?![A-Z0-9])",
    ))
    return company_pattern, raw_patterns, normalized_patterns


def _issuer_match_reason_prepared(raw_text: str, title: str, matcher: tuple) -> str:
    """Apply precompiled issuer patterns to already-cleaned raw/normalized text."""
    if not title:
        return ""
    company_pattern, raw_patterns, normalized_patterns = matcher
    if company_pattern is not None and company_pattern.search(title):
        return "COMPANY_NAME_MATCH"
    if any(pattern.search(raw_text) for pattern in raw_patterns):
        return "EXPLICIT_TICKER_MATCH"
    if any(pattern.search(title) for pattern in normalized_patterns):
        return "EXPLICIT_TICKER_MATCH"
    return ""


def _issuer_match_reason(symbol: str, headline: str, company: str = "") -> str:
    """Match an issuer by registered name or explicit ticker; never by loose substring."""
    raw_text = _clean(headline or "")
    title = _norm(raw_text)
    if not str(symbol or "").strip() or not title:
        return ""
    return _issuer_match_reason_prepared(
        raw_text, title, _prepare_issuer_matcher(symbol, company)
    )


def _item_exact_symbols(item: ET.Element) -> set[str]:
    """Extract exact issuer symbols once per RSS item, not once per candidate."""
    found = set()
    for node in item.iter():
        local_name = str(node.tag).rsplit("}", 1)[-1].split(":")[-1].strip().lower()
        if local_name in {"symbol", "ticker", "securitysymbol", "scripsymbol"}:
            value = str(node.text or "").strip().upper()
            if value:
                found.add(value)
    return found


def _item_has_exact_symbol(item: ET.Element, symbol: str) -> bool:
    """Return true only when an official RSS/API symbol field equals the ticker."""
    wanted = str(symbol or "").strip().upper()
    return bool(wanted) and wanted in _item_exact_symbols(item)


def _is_market_quote_headline(headline: str) -> bool:
    """Reject quote/profile pages masquerading as dated secondary news."""
    title = _norm(headline)
    patterns = (
        r"\bSHARE PRICE\b.*\b(LIVE NSE|LIVE CHART|STOCK PRICE|PRICE TODAY|CHART)\b",
        r"\bSTOCK PRICE\b.*\b(LIVE NSE|LIVE CHART|TODAY|CHART|QUOTE)\b",
        r"\bLIVE NSE\b.*\b(SHARE PRICE|STOCK PRICE)\b",
        r"\bSTOCK QUOTE\b",
        r"\bPRICE CHART\b.*\bLIVE\b",
    )
    return any(re.search(pattern, title) for pattern in patterns)


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
    """Keep candidates that passed either upstream Delivery category.

    Category A (at least five trailing five-session averages >=60%) and Category B (at least five daily sessions >=60%) are independent upstream routes. News enrichment must not
    silently narrow the union to Category B only.
    """
    filtered = candidates.copy()
    before = len(filtered)
    has_a = "DeliveryCategoryAStatus" in filtered.columns
    has_b = "DeliveryCategoryBStatus" in filtered.columns

    if has_a or has_b:
        a_pass = (
            filtered["DeliveryCategoryAStatus"].astype(str).str.upper().str.strip().eq("PASS_ROLLING_5D_AVG_GE_60_AT_LEAST_5")
            if has_a else pd.Series(False, index=filtered.index)
        )
        b_pass = (
            filtered["DeliveryCategoryBStatus"].astype(str).str.upper().str.strip().eq("PASS_DAILY_DELIVERY_GE_60_AT_LEAST_5")
            if has_b else pd.Series(False, index=filtered.index)
        )
        keep = a_pass | b_pass
        filtered = filtered.loc[keep].copy()
        print(
            f"[NEWS-DIAG] Delivery A/B union: before={before}, after={len(filtered)}, "
            f"category_a_pass={int(a_pass.sum())}, category_b_pass={int(b_pass.sum())}, "
            f"union_pass={int(keep.sum())}; Category A OR Category B"
        )
    else:
        daily_cols = [c for c in filtered.columns if str(c).startswith("Delivery_")]
        if len(daily_cols) >= 5:
            daily = filtered[daily_cols].apply(pd.to_numeric, errors="coerce")
            daily_pass = daily.notna().sum(axis=1).eq(5) & daily.ge(60.0).all(axis=1)
            filtered = filtered[daily_pass].copy()
            print(f"[NEWS-DIAG] Legacy daily Delivery gate: before={before}, after={len(filtered)}, rule=each_of_5_sessions>=60%")
        elif "DeliveryFilterStatus" in filtered.columns:
            statuses = filtered["DeliveryFilterStatus"].astype(str).str.upper().str.strip()
            allowed = {
                "PASS_GE_60_PERCENT", "PASS_GT_60_PERCENT",
                "PASS_AT_OR_ABOVE_60_PERCENT", "PASS_A_OR_B", "PASS",
            }
            filtered = filtered[statuses.isin(allowed)].copy()
            print(f"[NEWS-DIAG] Legacy Delivery union status: before={before}, after={len(filtered)}")
        else:
            filtered = filtered.iloc[0:0].copy()
            print("[NEWS-DIAG] Delivery evidence/status missing; fail-closed with zero candidates.")
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
    """List of parsed feed items with explicit completeness/availability flags."""

    def __init__(self, items=(), *, partial: bool = False, available: bool = True):
        super().__init__(items)
        self.partial = partial
        self.available = available


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


def _nse_announcement_api_items(
    symbol: str, from_date, to_date,
    session: requests.Session | None = None,
    warm_session: bool = True,
) -> list[ET.Element]:
    """Fetch NSE announcements and log bounded raw-response diagnostics.

    Diagnostics report status, content type, byte count, payload type/count,
    field names and a few non-sensitive record summaries. The function does
    not weaken date cutoffs, infer missing announcements, or bypass access
    controls. An empty response remains empty evidence.
    """
    start = pd.Timestamp(from_date).strftime("%d-%m-%Y")
    end = pd.Timestamp(to_date).strftime("%d-%m-%Y")
    requested_symbol = str(symbol).strip().upper()
    session = session or requests.Session()
    session.headers.update({**HEADERS, "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements"})
    try:
        if warm_session:
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
            return _RSSItemList([], available=False)

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
        return _RSSItemList(items, partial=False, available=True)
    except Exception as exc:
        print(f"[NEWS-DIAG] NSE_ANNOUNCEMENT_API_FAIL symbol={requested_symbol} range={start}:{end} error={type(exc).__name__}: {exc}")
        return _RSSItemList([], available=False)


def _news_window_bounds(eod_date, scan_mode=None, now=None):
    """Return the news scan window as UTC bounds plus its IST display bounds.

    EOD mode: seven calendar dates inclusive, from 00:00 IST on EOD date - 6
    days through 22:00 IST on the EOD date.

    PREMARKET mode: seven calendar dates inclusive relative to the next entry
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
        start_ist = end_day - pd.Timedelta(days=6)
        end_ist = end_day + pd.Timedelta(hours=9, minutes=15)
    else:
        eod_day = pd.Timestamp(eod_date)
        eod_day = eod_day.tz_localize("Asia/Kolkata") if eod_day.tzinfo is None else eod_day.tz_convert("Asia/Kolkata")
        end_day = eod_day.normalize()
        start_ist = end_day - pd.Timedelta(days=6)
        end_ist = end_day + pd.Timedelta(hours=22)

    return (
        start_ist.tz_convert("UTC").to_pydatetime(),
        end_ist.tz_convert("UTC").to_pydatetime(),
        start_ist,
        end_ist,
        mode,
    )


def _premarket_news_status(official_count: int, secondary_count: int, api_covered: bool) -> str:
    """Classify PREMARKET news only from issuer-specific evidence/coverage.

    A global RSS feed containing an unrelated company's filing does not prove that
    this candidate's issuer was covered. A successful empty issuer-filtered NSE API
    response does count as candidate-specific coverage; a failed API does not.
    """
    if official_count > 0:
        return "OFFICIAL_NEWS_FOUND"
    if not api_covered:
        return "WAIT_FOR_DATA"
    if secondary_count > 0:
        return "SECONDARY_ONLY_UNVERIFIED"
    return "NO_NEWS_FOUND"




UPCOMING_EVENT_COLUMNS = [
    "EODDate", "TckrSymb", "EventType", "EventDate", "AnnouncementDate",
    "Headline", "Source", "SourceType", "URL", "Status", "LookbackDays",
    "DaysToEvent", "EventHorizonStatus",
]

_EVENT_KEYWORDS = re.compile(
    r"\b(result|results|financial results|quarterly results|board meeting|"
    r"dividend|bonus|stock split|split|buyback|buy-back|record date|"
    r"rights issue|agm|egm|annual general meeting|extraordinary general meeting|"
    r"fund raising|fundraising|preferential issue|qip|merger|acquisition|"
    r"scheme of arrangement|demerger|corporate action)\b",
    re.IGNORECASE,
)

def _event_type_from_text(text: str) -> str:
    value = _clean(text).lower()
    if re.search(r"\b(quarterly|financial|annual|half[- ]yearly|audited|unaudited)\b.{0,60}\b(results?|earnings?)\b|\b(results?|earnings?)\b.{0,60}\b(quarterly|financial|annual|half[- ]yearly|audited|unaudited)\b", value):
        return "RESULTS"
    if re.search(r"\bboard meeting\b", value):
        return "BOARD_MEETING"
    if re.search(r"\bdividend\b", value):
        return "DIVIDEND"
    if re.search(r"\bbonus\b", value):
        return "BONUS"
    if re.search(r"\b(stock )?split\b", value):
        return "STOCK_SPLIT"
    if re.search(r"\bbuy[- ]?back\b", value):
        return "BUYBACK"
    if re.search(r"\brecord date\b", value):
        return "RECORD_DATE"
    if re.search(r"\b(rights issue|preferential issue|qip|fund ?rais(ing|e))\b", value):
        return "FUNDRAISING_OR_ISSUE"
    if re.search(r"\b(agm|annual general meeting|egm|extraordinary general meeting)\b", value):
        return "SHAREHOLDER_MEETING"
    if re.search(r"\b(merger|acquisition|demerger|scheme of arrangement)\b", value):
        return "M_AND_A"
    if re.search(r"\bcorporate action\b", value):
        return "CORPORATE_ACTION"
    return "OTHER_OFFICIAL_EVENT"


def _explicit_dates_in_text(text: str) -> list:
    """Parse only explicit date-shaped strings; never infer a date from context."""
    patterns = [
        r"\b\d{4}-\d{1,2}-\d{1,2}\b",
        r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b",
        r"\b\d{1,2}[- ](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[- ,]+\d{2,4}\b",
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[ ,]+\d{1,2}(?:st|nd|rd|th)?[,]?[ ]+\d{4}\b",
        r"\b\d{1,2}(?:st|nd|rd|th)?[ ]+(?:of[ ]+)?(?:January|February|March|April|May|June|July|August|September|October|November|December)[ ,]+\d{4}\b",
    ]
    found = []
    for pattern in patterns:
        for match in re.finditer(pattern, text or "", re.IGNORECASE):
            raw = match.group(0).strip()
            try:
                stamp = pd.to_datetime(raw, errors="raise", dayfirst=True)
                if not pd.isna(stamp):
                    day = stamp.date()
                    if day not in found:
                        found.append(day)
            except (TypeError, ValueError, OverflowError):
                continue
    return sorted(found)


def _upcoming_event_rows_for_item(
    symbol: str, item: ET.Element, eod_date, scan_mode: str, lookback_days: int = 90
) -> list[dict[str, str]]:
    """Build official upcoming-event records from issuer-filtered NSE filings.

    Only explicit dates in the filing text are accepted. Publication dates are
    never substituted for event dates, and past dates are not labelled upcoming.
    """
    title = _item_text(item, "title")
    description = _item_text(item, "description", "summary", "attchmntText")
    text = " ".join(part for part in (title, description) if part).strip()
    if not text or not _EVENT_KEYWORDS.search(text):
        return []
    published = _published(item)
    announcement_date = ""
    if published is not None:
        announcement_date = published.astimezone(
            pd.Timestamp.now(tz="UTC").tzinfo
        ).isoformat()
        # Display announcement dates in exchange-local time.
        announcement_date = pd.Timestamp(published).tz_convert("Asia/Kolkata").strftime("%Y-%m-%d")
    mode = str(scan_mode or "EOD").upper()
    ref = pd.Timestamp.now(tz="Asia/Kolkata").date() if mode == "PREMARKET" else pd.Timestamp(eod_date).date()
    event_type = _event_type_from_text(text)
    future_dates = [d for d in _explicit_dates_in_text(text) if d > ref]
    source_url = _item_text(item, "link") or "https://www.nseindia.com/companies-listing/corporate-filings-announcements"
    base = {
        "EODDate": str(pd.Timestamp(eod_date).date()),
        "TckrSymb": symbol,
        "EventType": event_type,
        "AnnouncementDate": announcement_date,
        "Headline": title or text,
        "Source": "NSE India",
        "SourceType": "PRIMARY_OFFICIAL",
        "URL": source_url,
        "LookbackDays": str(int(lookback_days)),
    }
    if future_dates:
        rows = []
        for event_date in future_dates:
            days_to_event = (event_date - ref).days
            horizon_status = (
                "NEXT_20_CALENDAR_DAYS"
                if 1 <= days_to_event <= 20
                else "FUTURE_OUTSIDE_20_DAY_HORIZON"
            )
            rows.append({
                **base,
                "EventDate": event_date.isoformat(),
                "Status": "OFFICIAL_DATE_CONFIRMED",
                "DaysToEvent": str(days_to_event),
                "EventHorizonStatus": horizon_status,
            })
        return rows
    # Keep an explicit diagnostic row, but do not claim the event is upcoming.
    return [{
        **base, "EventDate": "", "Status": "DATE_NOT_FOUND_OR_NO_FUTURE_DATE",
        "DaysToEvent": "", "EventHorizonStatus": "NOT_CLASSIFIED_NO_FUTURE_DATE",
    }]


def _write_upcoming_events_report(
    symbols: set[str], event_rows: list[dict[str, str]], api_coverage: dict[str, bool], eod_date
) -> None:
    """Write one or more event/evidence status rows for every shortlist symbol."""
    Path("outputs").mkdir(parents=True, exist_ok=True)
    by_symbol: dict[str, list[dict[str, str]]] = {s: [] for s in sorted(symbols)}
    for row in event_rows:
        symbol = str(row.get("TckrSymb", "")).upper()
        if symbol in by_symbol:
            by_symbol[symbol].append(row)
    final_rows = []
    for symbol in sorted(symbols):
        rows = by_symbol.get(symbol, [])
        if rows:
            # De-duplicate identical event date/type/headline records.
            seen = set()
            for row in rows:
                key = (row.get("EventType"), row.get("EventDate"), row.get("Headline"))
                if key not in seen:
                    seen.add(key)
                    final_rows.append(row)
        elif api_coverage.get(symbol, False):
            final_rows.append({
                "EODDate": str(pd.Timestamp(eod_date).date()), "TckrSymb": symbol,
                "EventType": "", "EventDate": "", "AnnouncementDate": "",
                "Headline": "", "Source": "NSE India", "SourceType": "PRIMARY_OFFICIAL",
                "URL": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
                "Status": "NO_MATCHING_UPCOMING_EVENT_FOUND", "LookbackDays": "90",
                "DaysToEvent": "", "EventHorizonStatus": "NO_MATCHING_EVENT_FOUND",
            })
        else:
            final_rows.append({
                "EODDate": str(pd.Timestamp(eod_date).date()), "TckrSymb": symbol,
                "EventType": "", "EventDate": "", "AnnouncementDate": "",
                "Headline": "", "Source": "", "SourceType": "",
                "URL": "", "Status": "WAIT_FOR_DATA", "LookbackDays": "90",
                "DaysToEvent": "", "EventHorizonStatus": "WAIT_FOR_DATA",
            })
    out = pd.DataFrame(final_rows, columns=UPCOMING_EVENT_COLUMNS)
    out.to_csv("outputs/v8_upcoming_corporate_events.csv", index=False)
    print(
        f"[NEWS-DIAG] UPCOMING_EVENTS_REPORT path=outputs/v8_upcoming_corporate_events.csv "
        f"shortlist_symbols={len(symbols)} rows={len(out)} "
        f"confirmed={int((out['Status'] == 'OFFICIAL_DATE_CONFIRMED').sum()) if not out.empty else 0} "
        f"wait_for_data={int((out['Status'] == 'WAIT_FOR_DATA').sum()) if not out.empty else 0}"
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
        Path("outputs").mkdir(parents=True, exist_ok=True)
        pd.DataFrame(columns=UPCOMING_EVENT_COLUMNS).to_csv("outputs/v8_upcoming_corporate_events.csv", index=False)
        print("[NEWS-DIAG] UPCOMING_EVENTS_REPORT no shortlisted candidates; wrote empty report")
        return empty, {"NSE": "no shortlisted candidates", "secondary": "not checked"}

    symbols = set(candidates["TckrSymb"].tolist())
    names = _read_equity_master()
    # Precompile issuer matching once. NSE global RSS can contain thousands of
    # items; repeated normalization/regex compilation for every item × symbol
    # pair was the dominant CPU cost in the EOD news stage.
    issuer_matchers = {
        symbol: _prepare_issuer_matcher(symbol, names.get(symbol, ""))
        for symbol in symbols
    }
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
        f"calendar_days=7"
    )

    rows: list[dict[str, str]] = []
    status = {"NSE": "available", "secondary": "available"}
    nse_successes = 0
    nse_partial = False
    official_window_records = 0

    # Read each exchange feed once, then map company names/symbols to all RVOL > 1.5 candidates.
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
            exact_symbols = _item_exact_symbols(item)
            raw_match_text = _clean(match_text)
            normalized_match_text = _norm(raw_match_text)
            for symbol in symbols:
                match_reason = (
                    "EXACT_OFFICIAL_SYMBOL_FIELD"
                    if symbol in exact_symbols
                    else _issuer_match_reason_prepared(
                        raw_match_text, normalized_match_text, issuer_matchers[symbol]
                    )
                )
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

    # The public RSS feeds are global and can omit issuer-specific filings.
    # Query NSE's issuer/date-filtered official announcements endpoint for every
    # candidate. The normal News/Catalyst rows are still restricted to the exact
    # five-calendar-day window; a separate 90-day official announcement lookback
    # is used only to discover explicitly dated future corporate events.
    api_start_date = (pd.Timestamp(window_end_ist_date) - pd.Timedelta(days=90)).date()
    api_end_date = window_end_ist_date
    api_coverage: dict[str, bool] = {}
    upcoming_event_rows: list[dict[str, str]] = []
    # Issuer API requests are independent by symbol. Use a small bounded worker
    # pool with one warmed requests.Session per worker; preserve deterministic
    # processing order and keep the exact same 90-day evidence window.
    api_thread_state = local()

    def _fetch_issuer_announcements(symbol):
        session = getattr(api_thread_state, "session", None)
        if session is None:
            session = requests.Session()
            api_thread_state.session = session
            api_thread_state.warmed = False
        warm_session = not api_thread_state.warmed
        try:
            items = _nse_announcement_api_items(
                symbol, api_start_date, api_end_date,
                session=session, warm_session=warm_session,
            )
            api_thread_state.warmed = True
            return symbol, items
        except Exception as exc:
            print(
                f"[NEWS-DIAG] NSE_ANNOUNCEMENT_API_FETCH_FAIL symbol={symbol} "
                f"error={type(exc).__name__}: {exc}"
            )
            api_thread_state.warmed = True
            return symbol, _RSSItemList([], available=False)

    ordered_symbols = sorted(symbols)
    api_workers = min(4, len(ordered_symbols))
    print(f"[NEWS-DIAG] NSE_ANNOUNCEMENT_API_PARALLEL workers={api_workers} symbols={len(ordered_symbols)}")
    with ThreadPoolExecutor(max_workers=max(1, api_workers)) as executor:
        api_results = dict(executor.map(_fetch_issuer_announcements, ordered_symbols))

    for symbol in ordered_symbols:
        api_items = api_results[symbol]
        api_coverage[symbol] = bool(getattr(api_items, "available", True))
        api_matches = 0
        for item in api_items:
            title = _item_text(item, "title")
            description = _item_text(item, "description")
            issuer_fields = _item_text(item, "company", "symbol")
            exact_api_symbol = _item_text(item, "symbol").strip().upper() == symbol
            if not exact_api_symbol and _issuer_match_reason(symbol, " ".join((title, description, issuer_fields)), names.get(symbol, "")) == "":
                continue
            # Corporate-event scan uses the broader official announcement lookback,
            # but records only explicit future dates and never changes News window rules.
            upcoming_event_rows.extend(
                _upcoming_event_rows_for_item(symbol, item, eod_date, scan_mode, lookback_days=90)
            )
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

    _write_upcoming_events_report(symbols, upcoming_event_rows, api_coverage, eod_date)
    api_successes = sum(api_coverage.values())
    if nse_successes == 0:
        status["NSE"] = "available via issuer API" if api_successes else "unavailable"
    elif nse_successes < len(NSE_FEEDS) or nse_partial:
        status["NSE"] = "partly available"

    # Free Google News RSS helps discover independent press coverage. It never
    # upgrades itself to primary evidence; the NSE file remains authoritative.
    secondary_successes = 0
    secondary_partial = False

    def _fetch_secondary_symbol(symbol):
        company = names.get(symbol, "").strip()
        combined_items: list[ET.Element] = []
        item_keys: set[tuple[str, str]] = set()
        query_success = False
        symbol_partial = False
        query_diagnostics = []
        for query in _secondary_search_queries(symbol, company):
            try:
                fetched = _rss_items(GOOGLE_RSS_URL, {
                    "q": query, "hl": "en-IN", "gl": "IN", "ceid": "IN:en",
                })
                query_success = True
                partial = bool(getattr(fetched, "partial", False))
                symbol_partial = symbol_partial or partial
                query_diagnostics.append((query, len(fetched), partial, ""))
                for item in fetched:
                    key = (_item_text(item, "title").casefold(), _item_text(item, "link").casefold())
                    if key not in item_keys:
                        item_keys.add(key)
                        combined_items.append(item)
            except Exception as exc:
                query_diagnostics.append((query, 0, False, f"{type(exc).__name__}: {exc}"))
        return symbol, combined_items, query_success, symbol_partial, query_diagnostics

    secondary_workers = min(4, len(ordered_symbols))
    print(f"[NEWS-DIAG] SECONDARY_RSS_PARALLEL workers={secondary_workers} symbols={len(ordered_symbols)}")
    with ThreadPoolExecutor(max_workers=max(1, secondary_workers)) as executor:
        secondary_results = dict(
            (symbol, (items, success, partial, diagnostics))
            for symbol, items, success, partial, diagnostics
            in executor.map(_fetch_secondary_symbol, ordered_symbols)
        )

    for symbol in ordered_symbols:
        company = names.get(symbol, "").strip()
        combined_items, query_success, symbol_partial, query_diagnostics = secondary_results[symbol]
        for query, item_count, partial, error in query_diagnostics:
            if error:
                print(f"[NEWS-DIAG] SECONDARY_FEED_FETCH_FAIL symbol={symbol} query={query!r} error={error}")
            else:
                print(
                    f"[NEWS-DIAG] SECONDARY_QUERY symbol={symbol} query={query!r} "
                    f"items={item_count} partial={partial}"
                )
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
            if _is_market_quote_headline(title):
                print(f"[NEWS-DIAG] SECONDARY_QUOTE_PAGE_IGNORED symbol={symbol} headline={title[:160]!r}")
                continue
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
            subset=["TckrSymb", "PublishedAt", "Headline"], keep="first"
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
            news_status = _premarket_news_status(
                official_count=len(official),
                secondary_count=len(secondary),
                api_covered=api_coverage.get(symbol, False),
            )
            if not official.empty:
                chosen = official.iloc[0]
            elif not secondary.empty:
                chosen = secondary.iloc[0]
            else:
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
    candidates = candidates.sort_values("RVOL", ascending=False, na_position="last")
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
    pd.DataFrame(report_rows).to_csv("outputs/v8_catalyst_rvol_gt_1_5.csv", index=False)


def _telegram_observation_rows(report: pd.DataFrame | None,
                               result: pd.DataFrame | None,
                               limit: int | None = None) -> pd.DataFrame:
    """Return every liquidity-passed stock, overlaying later gate statuses."""
    if report is None or report.empty or "TckrSymb" not in report.columns:
        return pd.DataFrame()
    rows = report.copy()
    rows["TckrSymb"] = rows["TckrSymb"].fillna("").astype(str).str.strip().str.upper()
    rows = rows[rows["TckrSymb"].ne("")].drop_duplicates("TckrSymb", keep="first")

    # Merge later statuses without dropping liquidity-qualified rows that fail
    # a later technical, news, or final watchlist check.
    if result is not None and not result.empty and "TckrSymb" in result.columns:
        downstream = result.copy()
        downstream["TckrSymb"] = downstream["TckrSymb"].fillna("").astype(str).str.strip().str.upper()
        downstream = downstream.drop_duplicates("TckrSymb", keep="last").set_index("TckrSymb")
        columns = [c for c in downstream.columns if c in {
            "LiquidityFilterStatus", "LiquidityStatus", "LiquidityTier",
            "FundamentalScore", "Fundamental65PlusStatus", "FundamentalStatus",
            "FundamentalSource", "CoreTechnicalScreenStatus", "CandidateScreenStatus",
            "SetupType", "RSI14", "RSI14Previous", "RSIDirection", "RSIZone",
            "RSIBehaviour", "RSIRetestStatus", "RSIDivergenceStatus",
            "EMA20", "EMA44", "EMA44Position", "TrendClassification",
            "RVOL", "RelativeStrengthNifty", "SectorStrengthNifty", "SectorStrengthStatus",
            "RiskReward", "RiskRewardStatus", "NewsEvidenceStatus", "NewsPrimarySourceVerified",
            "EODWatchlistStatus", "DeliveryCategoryAStatus",
            "DeliveryCategoryBStatus", "AvgDelivery5D",
            "DeliveryDailyPassCount", "DeliveryARolling5DPassCount30D",
            "DeliveryACount30DStatus", "DeliveryBCount30DStatus",
            "DeliverySessions", "DeliveryMin5D",
            "LatestDeliveryPct", "ClsPric", "ValuationPriceINR",
            "ValuationStatus", "ValuationAsOfDate", "ValuationSource",
            "ValuationAssessmentStatus", "TrailingPE", "ForwardPE",
            "PriceToBook", "PriceToSales",
            "Sector", "SectorStrengthClassification", "SectorStrengthStatus",
            "MarketRegime", "MarketRegimeStatus", "NewsStatus",
            "NewsCatalyst", "NewsCatalystImpact", "NewsIndependentSources",
            "NewsPrimarySources", "TechnicalConfirmations",
            "IndependentConfirmationCategories", "Confirmation3Plus1",
            "MandatoryConfirmationStatus", "V8Score", "V8ScoreCoveragePct",
            "EntryPricePlan", "StopLossPlan", "TargetPricePlan", "TargetSource",
            "StructuralResistanceUsed", "StructuralResistanceSource",
            "RiskRewardReason", "ChaseStatus", "RiskControlStatus",
            "RiskControlReason", "StopDistancePct", "EODWatchlistReason",
            "EODLayerStatus", "TrendClassification", "EMA44SignalStatus",
            "BreakoutStatus", "PullbackStatus", "CandidateScreenReasons",
            "CoreTechnicalScreenReasons", "CoreTechnicalScreenWarnings",
            "NewsNegativePrimary", "NewsCatalystSource", "NewsCatalystPublishedAt",
        }]
        overlay = downstream[columns] if columns else downstream.iloc[:, 0:0]
        rows = rows.merge(overlay, how="left", left_on="TckrSymb", right_index=True,
                          suffixes=("", "_pipeline"), sort=False)

    liquidity_col = next((c for c in ("LiquidityFilterStatus", "LiquidityStatus",
                                      "LiquidityFilterStatus_pipeline", "LiquidityStatus_pipeline")
                          if c in rows.columns), None)
    if liquidity_col:
        status = rows[liquidity_col].fillna("").astype(str).str.upper()
        rows = rows[status.eq("PASS") | status.str.startswith("PASS_")].copy()

    tier_col = next((c for c in ("LiquidityTier", "LiquidityTier_pipeline") if c in rows.columns), None)
    if tier_col:
        tiers = {"STRONG": 0, "MEDIUM": 1, "LOW": 2}
        rows["_liquidity_order"] = rows[tier_col].fillna("WAIT_FOR_DATA").astype(str).str.upper().map(tiers).fillna(3)
        sort_cols, ascending = ["_liquidity_order"], [True]
        if "FundamentalScore" in rows.columns:
            rows["FundamentalScore"] = pd.to_numeric(rows["FundamentalScore"], errors="coerce")
            sort_cols.append("FundamentalScore")
            ascending.append(False)
        rows = rows.sort_values(sort_cols, ascending=ascending, na_position="last", kind="stable").drop(columns="_liquidity_order")
    if limit is not None:
        rows = rows.head(max(0, int(limit)))
    return rows.reset_index(drop=True)


def _upcoming_event_summaries() -> dict[str, str]:
    """Read NSE event dates; never infer an event date from announcement date."""
    try:
        events = pd.read_csv("outputs/v8_upcoming_corporate_events.csv")
    except Exception:
        return {}
    if events.empty or "TckrSymb" not in events.columns:
        return {}
    summaries: dict[str, list[str]] = {}
    for _, row in events.iterrows():
        symbol = str(row.get("TckrSymb", "")).strip().upper()
        status = str(row.get("Status", "")).strip().upper()
        event_date = str(row.get("EventDate", "")).strip()
        if status == "OFFICIAL_DATE_CONFIRMED" and event_date:
            item = f"{event_date} {row.get('EventType', '')}".strip()
        elif status == "NO_MATCHING_UPCOMING_EVENT_FOUND":
            item = "NSE: पुढील event date सापडली नाही"
        else:
            item = "Event date WAIT_FOR_DATA"
        if symbol:
            summaries.setdefault(symbol, [])
            if item not in summaries[symbol]:
                summaries[symbol].append(item)
    return {symbol: " / ".join(items) for symbol, items in summaries.items()}


def _telegram_news_lines(news: pd.DataFrame | None, symbol: str, limit: int = 2) -> list[str]:
    """Return a small, source-labelled headline sentiment digest for one symbol."""
    if news is None or news.empty or not {"TckrSymb", "Headline"}.issubset(news.columns):
        return ["   📰 News: no matched headline in this scan window."]
    matched = news[
        news["TckrSymb"].fillna("").astype(str).str.strip().str.upper().eq(symbol.upper())
    ].copy()
    if matched.empty:
        return ["   📰 News: no matched headline in this scan window."]

    matched["_source_priority"] = matched.get(
        "SourceType", pd.Series("", index=matched.index)
    ).fillna("").astype(str).str.lower().map(
        {"primary": 0, "official": 0, "exchange": 0, "company": 0, "regulator": 0, "secondary": 1}
    ).fillna(2)
    matched["_published_sort"] = pd.to_datetime(
        matched.get("PublishedAt", pd.Series("", index=matched.index)),
        errors="coerce", utc=True,
    )
    matched = matched.sort_values(
        ["_source_priority", "_published_sort"], ascending=[True, False],
        na_position="last", kind="stable",
    )
    selected = []
    seen = set()
    for _, row in matched.iterrows():
        headline = _clean(str(row.get("Headline", "")))
        url = str(row.get("URL", "")).strip()
        key = (headline.casefold(), url.casefold())
        if not headline or key in seen:
            continue
        seen.add(key)
        selected.append(row)
        if len(selected) >= max(1, int(limit)):
            break

    lines = []
    for row in selected:
        impact = str(row.get("Impact", "")).strip().lower()
        if impact == "positive":
            sentiment = "🟢 POSITIVE / सकारात्मक"
        elif impact == "negative":
            sentiment = "🔴 NEGATIVE / नकारात्मक"
        else:
            sentiment = "⚪ UNCLEAR / स्पष्ट संकेत नाही"
        source_type = str(row.get("SourceType", "news")).strip().upper()
        source = _clean(str(row.get("Source", ""))) or source_type
        headline = _clean(str(row.get("Headline", "")))[:180]
        lines.append(f"   📰 {sentiment} • {source}: {headline}")
        url = str(row.get("URL", "")).strip()
        if url and url.lower() not in {"nan", "none"}:
            lines.append(f"      Link: {url[:1200]}")
    return lines or ["   📰 News: no matched headline in this scan window."]


def _top_ranked_observations_by_tier(selected: pd.DataFrame, limit_per_tier: int = 4) -> pd.DataFrame:
    """Return up to four fully evidenced candidates independently per liquidity tier."""
    if selected is None or selected.empty:
        return pd.DataFrame()
    rows = selected.copy()
    required = ["FundamentalScore", "RelativeStrengthNifty", "SectorStrengthNifty", "RVOL", "RiskReward", "EMA44"]
    for column in required:
        if column not in rows.columns:
            return rows.iloc[0:0].copy()
        rows[column] = pd.to_numeric(rows[column], errors="coerce")
    trend = rows.get("TrendClassification", pd.Series("", index=rows.index)).fillna("").astype(str)
    technical = rows.get("CoreTechnicalScreenStatus", rows.get("CandidateScreenStatus", pd.Series("", index=rows.index))).fillna("").astype(str).str.upper()
    rr_status = rows.get("RiskRewardStatus", pd.Series("", index=rows.index)).fillna("").astype(str).str.upper()
    news = rows.get("NewsEvidenceStatus", pd.Series("", index=rows.index)).fillna("").astype(str).str.upper()
    setup = rows.get("SetupType", pd.Series("", index=rows.index)).fillna("").astype(str)
    verified = rows.get("NewsPrimarySourceVerified", pd.Series(False, index=rows.index)).fillna(False).astype(str).str.upper().isin(["TRUE", "1", "YES"])
    eligible = (
        rows[required].notna().all(axis=1)
        & trend.str.contains("Bullish", case=False, regex=False)
        & technical.eq("PASS")
        & rr_status.eq("PASS")
        & rows["RiskReward"].ge(2.0)
        & news.eq("PRIMARY_CONFIRMED")
        & verified
        & setup.isin(["Breakout", "Pullback", "Pre-Breakout", "Possible Pullback"])
    )
    rows = rows[eligible].copy()
    tier_col = "LiquidityTier" if "LiquidityTier" in rows.columns else "LiquidityTier_pipeline"
    if rows.empty or tier_col not in rows.columns:
        return rows.iloc[0:0].copy()
    rows["_setup_rank"] = rows["SetupType"].map({"Breakout": 0, "Pullback": 1, "Pre-Breakout": 2, "Possible Pullback": 3}).fillna(4)
    groups = []
    for tier in ("STRONG", "MEDIUM", "LOW"):
        group = rows[rows[tier_col].fillna("").astype(str).str.upper().eq(tier)].copy()
        group = group.sort_values(
            ["FundamentalScore", "_setup_rank", "RelativeStrengthNifty", "SectorStrengthNifty", "RVOL", "RiskReward"],
            ascending=[False, True, False, False, False, False],
            na_position="last", kind="stable",
        ).head(max(0, int(limit_per_tier)))
        group["_TierRank"] = range(1, len(group) + 1)
        groups.append(group)
    return pd.concat(groups, ignore_index=True) if groups else rows.iloc[0:0].copy()


def _observation_digest_lines(report: pd.DataFrame | None,
                              result: pd.DataFrame | None = None,
                              news_data: pd.DataFrame | None = None,
                              company_names: dict[str, str] | None = None) -> list[str]:
    """Send every liquidity-passed stock with downstream confirmations and compact 30-day Delivery A/B counts."""
    rows = _telegram_observation_rows(report, result, limit=None)
    if rows.empty:
        return ["", "🔎 Liquidity filter नंतर Telegram साठी stock उपलब्ध नाही.",
                "Liquidity filter नंतर कोणताही verified stock उपलब्ध नाही. Liquidity audit आणि WAIT_FOR_DATA reports तपासा."]

    def value(row, column, default="WAIT_FOR_DATA"):
        raw = row.get(column, default)
        if raw is None or pd.isna(raw) or str(raw).strip() in {"", "nan", "None"}:
            return default
        return str(raw).strip()

    def number(row, column, suffix="", digits=2, default="WAIT"):
        raw = pd.to_numeric(pd.Series([row.get(column)]), errors="coerce").iloc[0]
        return f"{raw:.{digits}f}{suffix}" if pd.notna(raw) else default

    tier_col = "LiquidityTier" if "LiquidityTier" in rows.columns else "LiquidityTier_pipeline"
    tier_rank = {"STRONG": 0, "MEDIUM": 1, "LOW": 2}
    rows["_tier_rank"] = rows.get(tier_col, pd.Series("UNKNOWN", index=rows.index)).fillna("UNKNOWN").astype(str).str.upper().map(tier_rank).fillna(3)
    if "FundamentalScore" in rows.columns:
        rows["FundamentalScore"] = pd.to_numeric(rows["FundamentalScore"], errors="coerce")
        rows = rows.sort_values(["_tier_rank", "FundamentalScore", "TckrSymb"],
                                ascending=[True, False, True], na_position="last", kind="stable")
    else:
        rows = rows.sort_values(["_tier_rank", "TckrSymb"], kind="stable")
    rows = rows.drop(columns=["_tier_rank"])

    tier_counts = rows.get(tier_col, pd.Series("UNKNOWN", index=rows.index)).fillna("UNKNOWN").astype(str).str.upper().value_counts().to_dict()
    # Show the actual new 30-calendar-day Delivery A/B eligibility totals up front.
    # A = count of rolling five-valid-session averages >=60%; B = count of daily
    # sessions >=60%. Each route passes at five qualifying observations; eligibility
    # is A OR B. These are summaries of the liquidity-passed rows, not raw universe totals.
    a_statuses = rows.get("DeliveryACount30DStatus", pd.Series("WAIT_FOR_DATA", index=rows.index)).fillna("WAIT_FOR_DATA").astype(str).str.upper()
    b_statuses = rows.get("DeliveryBCount30DStatus", pd.Series("WAIT_FOR_DATA", index=rows.index)).fillna("WAIT_FOR_DATA").astype(str).str.upper()
    a_pass = int(a_statuses.eq("PASS").sum())
    b_pass = int(b_statuses.eq("PASS").sum())
    ab_union = int((a_statuses.eq("PASS") | b_statuses.eq("PASS")).sum())
    a_wait = int(a_statuses.str.startswith("WAIT").sum())
    b_wait = int(b_statuses.str.startswith("WAIT").sum())
    core_col = "CoreTechnicalScreenStatus" if "CoreTechnicalScreenStatus" in rows.columns else "CandidateScreenStatus"
    core_status = rows.get(core_col, pd.Series("WAIT_FOR_DATA", index=rows.index)).fillna("WAIT_FOR_DATA").astype(str).str.upper()
    core_pass = rows.loc[core_status.eq("PASS"), "TckrSymb"].astype(str).tolist()
    fully_confirmed = _top_ranked_observations_by_tier(rows, limit_per_tier=4)
    mandatory = rows.get("MandatoryConfirmationStatus", pd.Series("WAIT_FOR_DATA", index=rows.index)).fillna("WAIT_FOR_DATA").astype(str).str.upper()
    rr = rows.get("RiskRewardStatus", pd.Series("WAIT_FOR_DATA", index=rows.index)).fillna("WAIT_FOR_DATA").astype(str).str.upper()
    risk = rows.get("RiskControlStatus", pd.Series("WAIT_FOR_DATA", index=rows.index)).fillna("WAIT_FOR_DATA").astype(str).str.upper()
    final = rows.get("EODWatchlistStatus", pd.Series("WAIT_FOR_DATA", index=rows.index)).fillna("WAIT_FOR_DATA").astype(str).str.upper()

    lines = [
        "",
        f"📋 LIQUIDITY-PASSED FULL AUDIT • एकूण {len(rows)} stocks",
        f"🟢 STRONG: {tier_counts.get('STRONG', 0)} | 🟡 MEDIUM: {tier_counts.get('MEDIUM', 0)} | 🔵 WEAK: {tier_counts.get('LOW', 0)}",
        f"📦 DELIVERY A/B (30D): A PASS {a_pass} | B PASS {b_pass} | A OR B eligible {ab_union}",
        f"⏳ Delivery WAIT: A {a_wait} | B {b_wait} | नियम: A rolling 5-session avg >=60% किमान 5 वेळा; B daily >=60% किमान 5 दिवस.",
        f"Core Technical PASS: {len(core_pass)} | Mandatory confirmation PASS: {int(mandatory.eq('PASS').sum())} | R:R PASS: {int(rr.eq('PASS').sum())}",
        f"Risk Control PASS: {int(risk.eq('PASS').sum())} | Final WATCH: {int(final.isin(['WATCH', 'PASS']).sum())}",
        "खालील प्रत्येक stock साठी Delivery, RVOL, Liquidity, Fundamental, Technical, Sector, News, 3+1, R:R, Chase, Risk आणि Final status दिले आहेत.",
        "PASS = त्या layer मध्ये पास; FAIL/REJECT/SKIP = त्या layer मध्ये अयशस्वी; WAIT = पुरावा/डेटा अपुरा.",
    ]
    if core_pass:
        lines.append("⭐ CORE TECHNICAL PASS: " + ", ".join(core_pass))
    else:
        lines.append("⭐ CORE TECHNICAL PASS: या scan मध्ये नाही.")
    lines.append(f"Fully confirmed ranked stocks: {len(fully_confirmed)}")
    if fully_confirmed.empty:
        lines.append("सध्या ranked stock उपलब्ध नाही; कोणताही stock जबरदस्तीने निवडलेला नाही.")

    tier_headers = {
        "STRONG": "🟢 STRONG LIQUIDITY (≥₹5cr/day)",
        "MEDIUM": "🟡 MEDIUM LIQUIDITY (₹2–5cr/day)",
        "LOW": "🔵 WEAK LIQUIDITY (₹1.5–2cr/day)",
    }
    # Official NSE equity master is the only source of displayed company names.
    # Missing/unavailable mapping must never be guessed from a ticker.
    official_company_names = company_names if company_names is not None else _read_equity_master()
    current_tier = None
    for _, row in rows.iterrows():
        symbol = value(row, "TckrSymb", "UNKNOWN")
        tier = value(row, tier_col, "UNKNOWN").upper()
        if tier != current_tier:
            lines.extend(["", tier_headers.get(tier, f"⚪ {tier} LIQUIDITY")])
            current_tier = tier

        turnover = pd.to_numeric(pd.Series([row.get("AvgDailyTradedValue20D")]), errors="coerce").iloc[0]
        turnover_text = f"₹{turnover / 10_000_000:.2f}cr/day" if pd.notna(turnover) else "turnover WAIT"
        avg_delivery = number(row, "AvgDelivery30D", "%", 1, "WAIT")
        a_status = value(row, "DeliveryCategoryAStatus")
        b_status = value(row, "DeliveryCategoryBStatus")
        a_short = "PASS" if a_status.startswith("PASS") else ("WAIT" if a_status.startswith("WAIT") else "FAIL")
        b_short = "PASS" if b_status.startswith("PASS") else ("WAIT" if b_status.startswith("WAIT") else "FAIL")
        rvol = number(row, "RVOL", "x", 2)
        fund_status = value(row, "FundamentalStatus")
        fund_score = number(row, "FundamentalScore", "/100", 1)
        technical = value(row, core_col)
        setup = value(row, "SetupType")
        trend = value(row, "TrendClassification")
        ema_signal = value(row, "EMA44SignalStatus")
        sector = value(row, "Sector", "Unknown")
        sector_status = value(row, "SectorStrengthStatus")
        news_status = value(row, "NewsEvidenceStatus")
        news_verified = value(row, "NewsPrimarySourceVerified", "False")
        confirmation = value(row, "Confirmation3Plus1")
        mandatory_status = value(row, "MandatoryConfirmationStatus")
        rr_status = value(row, "RiskRewardStatus")
        rr_value = number(row, "RiskReward", "R", 2)
        chase = value(row, "ChaseStatus")
        risk_status = value(row, "RiskControlStatus")
        eod_status = value(row, "EODWatchlistStatus")
        def _s(val):
            v = str(val).upper()
            if v.startswith("PASS") or v in {"WATCH", "PASS_CORE_TECHNICAL_SCREEN", "RISK_LIMITS_PASSED"}:
                return "OK"
            if v.startswith("WAIT"):
                return "WAIT"
            if v.startswith("FAIL") or v.startswith("REJECT") or v.startswith("SKIP") or v.startswith("FILTERED"):
                return "FAIL"
            return "NA"

        official_name = official_company_names.get(symbol)
        lines.append("  Company: " + (official_name if official_name else "NAME_NOT_VERIFIED_IN_NSE_MASTER"))
        lines.append("  NSE: " + symbol + " | " + tier + " " + turnover_text)
        rvol_raw = value(row, "RVOLStatus")
        a_count = value(row, "DeliveryARolling5DPassCount30D", "WAIT")
        b_count = value(row, "DeliveryDailyPassCount", "WAIT")
        a_count_status = value(row, "DeliveryACount30DStatus", "WAIT_FOR_DATA")
        b_count_status = value(row, "DeliveryBCount30DStatus", "WAIT_FOR_DATA")
        a_count_tag = a_count_status if a_count_status in {"PASS", "FAIL"} else "WAIT"
        b_count_tag = b_count_status if b_count_status in {"PASS", "FAIL"} else "WAIT"
        lines.append("  Delivery: A " + str(a_count) + "/30 " + a_count_tag + " | B " + str(b_count) + "/30 " + b_count_tag + " | RVOL: " + str(rvol) + " " + _s(rvol_raw))
        lines.append("  Fund: " + str(fund_status) + " " + str(fund_score) + " " + _s(fund_status) + " | Technical:" + str(technical) + " (" + _s(technical) + ") | Setup: " + str(setup))
        lines.append("  Trend: " + str(trend) + " (" + _s(trend) + ") | EMA44: " + str(ema_signal) + " " + _s(ema_signal) + " | RSI: " + str(number(row, "RSI14", "", 1)))
        lines.append("  Sector:" + str(sector_status) + " (" + str(sector) + ") | News: " + str(news_status) + " " + _s(news_status) + " | 3+1:" + str(confirmation) + "/" + str(mandatory_status))
        lines.append("  R:R: " + str(rr_status) + " " + str(rr_value) + " " + _s(rr_status) + " | Chase: " + str(chase) + " " + _s(chase) + " | Risk:" + str(risk_status) + " " + _s(risk_status) + " | FINAL:" + str(eod_status) + " " + _s(eod_status))

        reasons = []
        for label, col in (
            ("Technical", "CoreTechnicalScreenReasons"),
            ("Sector", "SectorStrengthReason"),
            ("News", "NewsStatus"),
            ("R:R", "RiskRewardReason"),
            ("Risk", "RiskControlReason"),
            ("Final", "EODWatchlistReason"),
        ):
            reason = value(row, col, "")
            if reason and reason not in {"WAIT_FOR_DATA", "nan", "None"} and reason.upper() not in {"PASS", "PASS_CORE_TECHNICAL_SCREEN", "RISK_LIMITS_PASSED"}:
                reasons.append(f"{label}:{reason[:180]}")
        if reasons:
            lines.append("  कारण: " + " | ".join(reasons))

        catalyst = value(row, "NewsCatalyst", "")
        if catalyst:
            lines.append("  News/Catalyst: " + catalyst[:180])
    lines.extend([
        "",
        "RSI patterns: Retest/Divergence = NOT_EVALUATED (informational only; no stock rejection).",
        "RSI/Overbought हे informational आहेत; RSI मुळे stock reject केलेला नाही.",
        "ही screening report आहे; BUY recommendation किंवा automatic order नाही. WAIT_FOR_DATA ला PASS समजू नका.",
    ])
    return lines

def build_marathi_digest(result: pd.DataFrame, eod_date, news: pd.DataFrame, feed_status: dict[str, str], observation_report: pd.DataFrame | None = None) -> list[str]:
    """Build a capped Telegram digest with current statuses for filtered names."""
    scan_mode = str(os.getenv("NEWS_SCAN_MODE", "EOD")).strip().upper()
    heading = "🌅 NSE V8 • PRE-MARKET" if scan_mode == "PREMARKET" else "📊 NSE V8 • EOD"
    status_col = result.get("EODWatchlistStatus", pd.Series("WAIT_FOR_DATA", index=result.index)).fillna("WAIT_FOR_DATA").astype(str).str.upper() if isinstance(result, pd.DataFrame) else pd.Series(dtype=str)
    counts = status_col.value_counts().to_dict()
    waiting = sum(v for k, v in counts.items() if k.startswith("WAIT"))
    # Generation time is not the same as the upstream market-data update time.
    generated_at_ist = pd.Timestamp.now(tz="Asia/Kolkata").to_pydatetime()
    lines = [f"{heading} • {eod_date}",
             f"📅 EOD Data Date: {eod_date} | 🕒 Report Generated: {generated_at_ist:%Y-%m-%d %H:%M:%S} IST",
             "🕒 Last Source Data Update: WAIT_FOR_VERIFIED_TIMESTAMP",
             f"Liquidity/Fundamental pipeline rows: {len(result)} | Final WATCH: {counts.get('WATCH', 0)} | WAIT: {waiting}"]
    if scan_mode == "PREMARKET":
        lines.append("News refresh only • Technical status मागील EOD scan मधील आहे.")
    official_company_names = _read_equity_master()
    lines.extend(build_telegram_research_sections(result, news, eod_date, official_company_names))
    lines.extend(_observation_digest_lines(observation_report, result, news, official_company_names))
    lines.append("News sentiment headline/description वर आधारित आहे; पूर्ण बातमी वाचल्याची किंवा स्वतंत्र पुष्टीची हमी नाही.")
    lines.append("रिकामी/unverified माहिती WAIT_FOR_DATA राहते. हा अहवाल BUY शिफारस नाही; automatic order नाही.")
    return lines

def send_marathi_telegram(result: pd.DataFrame, eod_date, news: pd.DataFrame, feed_status: dict[str, str], token: str | None, chat_id: str | None, observation_report: pd.DataFrame | None = None) -> None:
    """Send the complete scan digest and verify Telegram's acknowledgement."""
    import time

    if not token or not chat_id:
        raise RuntimeError("Telegram enabled but TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID is missing; configure both GitHub Actions secrets.")

    lines = build_marathi_digest(result, eod_date, news, feed_status, observation_report)
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
    if not chunks:
        chunks = [f"NSE V8 Scan completed | {eod_date}\nरिपोर्टमध्ये दाखवण्यासाठी डेटा उपलब्ध नाही."]

    for index, chunk in enumerate(chunks, start=1):
        message = f"भाग {index}/{len(chunks)}\n{chunk}" if len(chunks) > 1 else chunk
        last_error = None
        for attempt in range(1, 4):
            try:
                response = requests.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    data={"chat_id": chat_id, "text": message, "disable_web_page_preview": True},
                    timeout=25,
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict) or payload.get("ok") is not True:
                    raise RuntimeError(f"Telegram API rejected message: {payload}")
                print(f"TELEGRAM_DELIVERED part={index}/{len(chunks)} message_id={payload.get('result', {}).get('message_id')}")
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                print(f"Telegram send failed part={index}/{len(chunks)} attempt={attempt}/3: {type(exc).__name__}: {exc}")
                if attempt < 3:
                    time.sleep(2 ** attempt)
        if last_error is not None:
            raise RuntimeError(f"Telegram delivery failed for part {index}/{len(chunks)} after 3 attempts") from last_error
