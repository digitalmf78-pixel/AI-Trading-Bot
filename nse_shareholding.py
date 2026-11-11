"""Public NSE shareholding-pattern XBRL collector (no API key).

The filing index is read from NSE's public corporate-shareholding page endpoint.
Each selected XML file is downloaded only from the official nsearchives.nseindia.com
host and parsed as a point-in-time filing. The output is enrichment-only and does
not modify eligibility, ranking or Fundamental Score.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

NSE_HOME = "https://www.nseindia.com/"
NSE_SHAREHOLDING_PAGE = "https://www.nseindia.com/companies-listing/corporate-filings-shareholding-pattern/"
NSE_SHAREHOLDING_API = "https://www.nseindia.com/api/corporate-share-holdings-master"
NSE_XBRL_HOST = "nsearchives.nseindia.com"

# These are exact XBRL dimension member names used in NSE's SHP taxonomy.
_MEMBER_TO_METRIC = {
    "shareholdingofpromoterandpromotergroupmember": "PromoterHoldingPct",
    "publicshareholdingmember": "PublicHoldingPct",
    "institutionsforeignmember": "FIIHoldingPct",
    "institutionsdomesticmember": "DIIHoldingPct",
}
_PERCENT_FACT_TAGS = {
    "shareholdingasapercentageoftotalnumberofshares",
}
METRICS = tuple(_MEMBER_TO_METRIC.values())


def _local(value: Any) -> str:
    """Return the local part of an XML QName or prefixed lexical QName."""
    text = str(value or "")
    if "}" in text:
        text = text.rsplit("}", 1)[-1]
    if ":" in text:
        text = text.rsplit(":", 1)[-1]
    return text


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", _local(value).lower())


def _as_date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%d-%m-%Y", "%Y-%m-%d",
                "%d/%m/%Y", "%d-%b-%y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.date().isoformat()
    except ValueError:
        return ""


def _numeric_fact(node: ET.Element) -> float | None:
    raw = (node.text or "").strip()
    if not raw:
        return None
    try:
        value = Decimal(raw)
        scale = node.attrib.get("scale", "")
        if scale:
            value *= Decimal(10) ** int(scale)
        if node.attrib.get("sign") == "-":
            value = -value
        result = float(value)
    except (InvalidOperation, ValueError, TypeError, OverflowError):
        return None
    if not (result == result and abs(result) != float("inf")):
        return None
    return result


def _contexts(root: ET.Element) -> dict[str, dict]:
    contexts: dict[str, dict] = {}
    for node in root.iter():
        if _norm(node.tag) != "context":
            continue
        context_id = node.attrib.get("id", "")
        period = {}
        for child in node.iter():
            name = _norm(child.tag)
            if name in {"instant", "startdate", "enddate"}:
                period[name] = _as_date(child.text)
        members = []
        for child in node.iter():
            if _norm(child.tag) != "explicitmember":
                continue
            member = _norm(child.text)
            dimension = _norm(child.attrib.get("dimension", ""))
            if member:
                members.append({"dimension": dimension, "member": member})
        entity_identifier = ""
        for child in node.iter():
            if _norm(child.tag) == "identifier":
                entity_identifier = (child.text or "").strip()
                break
        contexts[context_id] = {
            "period": period,
            "members": members,
            "entity_identifier": entity_identifier,
        }
    return contexts


def parse_shareholding_xbrl(
    xml_content: bytes | str,
    *,
    expected_period_end: str = "",
) -> dict:
    """Extract promoter/public/FII/DII percentages from one official SHP XBRL.

    Exact, unambiguous dimension facts are required. Percentage scale is
    auto-detected from the promoter + public roll-up to support both legacy
    basis-point-style files and the newer fractional taxonomy representation.
    """
    root = ET.fromstring(xml_content)
    contexts = _contexts(root)
    expected = _as_date(expected_period_end)
    candidates: dict[str, list[dict]] = {metric: [] for metric in METRICS}

    for node in root.iter():
        if _norm(node.tag) not in _PERCENT_FACT_TAGS:
            continue
        context_ref = node.attrib.get("contextRef", "")
        context = contexts.get(context_ref)
        if not context:
            continue
        period = context["period"]
        observed_period = period.get("instant") or period.get("enddate", "")
        if expected and observed_period != expected:
            continue
        # Reject segmented/combined rows; the roll-up fact must contain no
        # more than two explicit dimensions (category plus possible share class).
        members = context["members"]
        if not members or len(members) > 2:
            continue
        value = _numeric_fact(node)
        if value is None:
            continue
        for member in members:
            metric = _MEMBER_TO_METRIC.get(member["member"])
            if metric:
                candidates[metric].append({
                    "value": value,
                    "dimension_count": len(members),
                    "context_ref": context_ref,
                    "entity_identifier": context["entity_identifier"],
                })

    raw_values: dict[str, float] = {}
    details: dict[str, dict] = {}
    for metric, rows in candidates.items():
        if not rows:
            continue
        best_dimension_count = min(row["dimension_count"] for row in rows)
        best = [row for row in rows if row["dimension_count"] == best_dimension_count]
        distinct = {round(float(row["value"]), 8) for row in best}
        if len(distinct) != 1:
            return {
                "status": "AMBIGUOUS_DIMENSIONAL_FACTS",
                "metrics": {},
                "reason": f"{metric}: conflicting roll-up facts found for the same reporting period",
                "candidate_counts": {key: len(value) for key, value in candidates.items()},
                "expected_period_end": expected,
            }
        raw_values[metric] = float(next(iter(distinct)))
        details[metric] = {
            "context_ref": best[0]["context_ref"],
            "entity_identifier": best[0]["entity_identifier"],
            "dimension_count": best_dimension_count,
        }

    if not raw_values:
        return {
            "status": "NO_MAPPED_SHAREHOLDING_FACTS",
            "metrics": {},
            "reason": "No exact unambiguous NSE shareholding percentage facts were found for the requested reporting period",
            "candidate_counts": {key: len(value) for key, value in candidates.items()},
            "expected_period_end": expected,
        }

    # NSE taxonomy vintages encode the same percentages differently. Prefer
    # a scale inferred from the promoter/public total; never scale per metric.
    scale = 1.0
    promoter = raw_values.get("PromoterHoldingPct")
    public = raw_values.get("PublicHoldingPct")
    if promoter is not None and public is not None:
        total = promoter + public
        if total > 1000:
            scale = 0.01
        elif 0 < total < 2:
            scale = 100.0
    else:
        observed = promoter if promoter is not None else public
        if observed is not None:
            if observed > 1000:
                scale = 0.01
            elif 0 < observed < 2:
                scale = 100.0

    normalized = {}
    for metric, value in raw_values.items():
        percent = value * scale
        if not (0 <= percent <= 100.5):
            return {
                "status": "INVALID_SHAREHOLDING_PERCENTAGE",
                "metrics": {},
                "reason": f"{metric} produced an out-of-range value after taxonomy scale normalization",
                "raw_value": value,
                "scale_factor": scale,
                "expected_period_end": expected,
            }
        normalized[metric] = round(percent, 6)

    total_pct = None
    total_check = "NOT_EVALUATED"
    if promoter is not None and public is not None:
        total_pct = round((promoter + public) * scale, 6)
        total_check = "WITHIN_2PP_OF_100" if abs(total_pct - 100.0) <= 2.0 else "OUTSIDE_2PP_OF_100"

    namespace = root.tag[1:].split("}", 1)[0] if str(root.tag).startswith("{") else ""
    return {
        "status": "DATA_FOUND",
        "metrics": normalized,
        "reason": "",
        "expected_period_end": expected,
        "taxonomy_namespace": namespace,
        "scale_factor": scale,
        "promoter_plus_public_pct": total_pct,
        "promoter_public_total_check": total_check,
        "candidate_counts": {key: len(value) for key, value in candidates.items()},
        "fact_details": details,
        "pledge_status": "NOT_MAPPED_FROM_CURRENT_NSE_FACT_CONTRACT",
    }


def _build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=2, connect=2, read=1, status=2,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; NSE-V8-Shareholding-Audit/1.0)",
        "Accept": "application/json,text/plain,application/xml,*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": NSE_SHAREHOLDING_PAGE,
        "X-Requested-With": "XMLHttpRequest",
    })
    return session


def _compact_filing(row: dict, symbol: str) -> dict:
    row_symbol = str(row.get("symbol", row.get("Symbol", "")) or "").strip().upper()
    if row_symbol and row_symbol != symbol:
        return {}
    xbrl_url = str(row.get("xbrl", row.get("xbrlUrl", "")) or "").strip()
    parsed = urlparse(xbrl_url)
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").lower() != NSE_XBRL_HOST
        or not parsed.path.lower().startswith("/corporate/xbrl/")
        or not parsed.path.lower().endswith(".xml")
    ):
        return {}
    return {
        "symbol": row_symbol or symbol,
        "date": str(row.get("date", "") or ""),
        "period_end": _as_date(row.get("date", "")),
        "submission_date": str(row.get("submissionDate", row.get("submission_date", "")) or ""),
        "broadcast_date": str(row.get("broadcastDate", row.get("broadcast_date", "")) or ""),
        "xbrl": xbrl_url,
        "record_id": str(row.get("recordId", row.get("record_id", "")) or ""),
        "revised": str(row.get("revisedData", row.get("revised", "")) or ""),
    }


def _date_sort_value(value: str) -> str:
    return _as_date(value) or ""


def _load_or_fetch_filing(
    symbol: str,
    *,
    cache_dir: str | Path,
    session_factory=None,
    now: datetime | None = None,
    max_age_days: int = 7,
) -> tuple[dict | None, dict]:
    base = Path(cache_dir)
    index_dir = base / "filing_index"
    index_dir.mkdir(parents=True, exist_ok=True)
    cache_path = index_dir / f"{symbol}.json"
    current = now or datetime.now(timezone.utc)

    if cache_path.is_file():
        age_seconds = current.timestamp() - cache_path.stat().st_mtime
        if 0 <= age_seconds < max(1, max_age_days) * 86400:
            try:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                raw_filing = cached.get("latest_filing")
                filing = _compact_filing(raw_filing, symbol) if isinstance(raw_filing, dict) else {}
                if filing and filing.get("period_end"):
                    return filing, {
                        "index_status": "REUSED_CACHE",
                        "index_checked_at_utc": cached.get("checked_at_utc", ""),
                    }
                if cached.get("status") == "NO_FILING":
                    return None, {
                        "index_status": "REUSED_EMPTY_CACHE",
                        "index_checked_at_utc": cached.get("checked_at_utc", ""),
                    }
            except (OSError, ValueError, TypeError):
                pass

    session = session_factory() if session_factory else _build_session()
    warmup_status = "NOT_ATTEMPTED"
    try:
        try:
            warmup = session.get(NSE_HOME, timeout=(5, 12))
            warmup_status = f"HTTP_{getattr(warmup, 'status_code', 200)}"
        except requests.RequestException as exc:
            # Warm-up is diagnostic; the official API request still gets one
            # attempt with the same session. No anti-bot or CAPTCHA bypass.
            warmup_status = f"ERROR:{type(exc).__name__}"
        response = session.get(
            NSE_SHAREHOLDING_API,
            params={"index": "equities", "symbol": symbol},
            headers={"Referer": NSE_SHAREHOLDING_PAGE, "Accept": "*/*"},
            timeout=(5, 20),
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict):
            for key in ("data", "records", "results", "shareholdingPatterns"):
                if isinstance(payload.get(key), list):
                    payload = payload[key]
                    break
        if not isinstance(payload, list):
            raise ValueError(f"Unexpected NSE shareholding index response: {type(payload).__name__}")
        filings = [
            compact for row in payload if isinstance(row, dict)
            if (compact := _compact_filing(row, symbol))
        ]
        filings.sort(
            key=lambda row: (
                _date_sort_value(row.get("period_end", "")),
                _date_sort_value(row.get("submission_date", "")),
                str(row.get("broadcast_date", "")),
                str(row.get("revised", "")).upper() == "Y",
            ),
            reverse=True,
        )
        latest = filings[0] if filings else None
        stored = {
            "symbol": symbol,
            "checked_at_utc": current.isoformat(),
            "status": "DATA_FOUND" if latest else "NO_FILING",
            "filing_count": len(filings),
            "latest_filing": latest,
        }
        tmp_path = cache_path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(stored, indent=2, sort_keys=True), encoding="utf-8")
        tmp_path.replace(cache_path)
        return latest, {
            "index_status": "FETCHED" if latest else "NO_FILING_FOUND",
            "index_checked_at_utc": current.isoformat(),
            "index_filing_count": len(filings),
            "homepage_warmup_status": warmup_status,
        }
    except (requests.RequestException, ValueError, TypeError, OSError) as exc:
        return None, {
            "index_status": "PROVIDER_ERROR",
            "reason": f"{type(exc).__name__}: {str(exc)[:300]}",
            "homepage_warmup_status": warmup_status,
        }


def fetch_nse_shareholding_metrics(
    symbol: str,
    *,
    cache_dir: str | Path = "data/cache/shareholding_xbrl",
    session_factory=None,
    xbrl_fetcher=None,
    now: datetime | None = None,
    max_index_age_days: int = 7,
) -> dict:
    """Fetch the latest official NSE SHP XBRL for one NSE main-board symbol."""
    symbol = str(symbol or "").strip().upper()
    attempted_at = (now or datetime.now(timezone.utc)).isoformat()
    empty = {
        "symbol": symbol,
        "metrics": {},
        "metric_sources": {},
        "metric_urls": {},
        "metric_periods": {},
        "metric_currencies": {},
        "provider": {},
        "attempted_at_utc": attempted_at,
    }
    if not symbol or not re.fullmatch(r"[A-Z0-9&._-]{1,30}", symbol):
        empty["provider"] = {"status": "INVALID_SYMBOL", "reason": "Expected one uppercase NSE symbol"}
        return empty

    filing, index_diag = _load_or_fetch_filing(
        symbol, cache_dir=cache_dir, session_factory=session_factory,
        now=now, max_age_days=max_index_age_days,
    )
    if filing is None:
        empty["provider"] = {
            "status": "NO_FILING_FOUND" if index_diag.get("index_status") == "REUSED_EMPTY_CACHE" else index_diag.get("index_status", "NO_FILING_FOUND"),
            "source_url": NSE_SHAREHOLDING_PAGE,
            **index_diag,
        }
        return empty

    filing_url = filing["xbrl"]
    period_end = filing.get("period_end", "")
    if not period_end:
        empty["provider"] = {
            "status": "FILING_PERIOD_MISSING",
            "reason": "NSE shareholding filing index did not supply a reporting period date",
            "source_url": filing_url,
            "index_diagnostics": index_diag,
        }
        return empty
    digest = hashlib.sha256(filing_url.encode("utf-8")).hexdigest()[:20]
    xml_dir = Path(cache_dir) / "xbrl"
    xml_dir.mkdir(parents=True, exist_ok=True)
    xml_path = xml_dir / f"{digest}.xml"
    xbrl_cache_status = "REUSED_CACHE"
    try:
        if not xml_path.is_file() or xml_path.stat().st_size < 100:
            fetcher = xbrl_fetcher
            if fetcher is None:
                from nse_xbrl_fetch import fetch_official_xbrl_xml
                fetcher = fetch_official_xbrl_xml
            fetcher(filing_url, xml_path, attempts=2)
            xbrl_cache_status = "DOWNLOADED"
        parsed = parse_shareholding_xbrl(
            xml_path.read_bytes(), expected_period_end=period_end,
        )
    except Exception as exc:
        empty["provider"] = {
            "status": "XBRL_FETCH_OR_PARSE_ERROR",
            "reason": f"{type(exc).__name__}: {str(exc)[:300]}",
            "source_url": filing_url,
            "filing_period_end": period_end,
            "submission_date": filing.get("submission_date", ""),
            "broadcast_date": filing.get("broadcast_date", ""),
            "index_diagnostics": index_diag,
        }
        return empty

    provider = {
        "status": parsed.get("status", "UNKNOWN"),
        "reason": parsed.get("reason", ""),
        "source_url": filing_url,
        "filing_index_url": NSE_SHAREHOLDING_PAGE,
        "filing_period_end": period_end,
        "submission_date": filing.get("submission_date", ""),
        "broadcast_date": filing.get("broadcast_date", ""),
        "record_id": filing.get("record_id", ""),
        "revised": filing.get("revised", ""),
        "taxonomy_namespace": parsed.get("taxonomy_namespace", ""),
        "scale_factor": parsed.get("scale_factor", ""),
        "promoter_plus_public_pct": parsed.get("promoter_plus_public_pct", ""),
        "promoter_public_total_check": parsed.get("promoter_public_total_check", ""),
        "pledge_status": parsed.get("pledge_status", "NOT_MAPPED_FROM_CURRENT_NSE_FACT_CONTRACT"),
        "xbrl_cache_status": xbrl_cache_status,
        "xbrl_sha256": hashlib.sha256(xml_path.read_bytes()).hexdigest(),
        "xbrl_cache_path": str(xml_path),
        "index_diagnostics": index_diag,
    }
    empty["provider"] = provider
    if parsed.get("status") != "DATA_FOUND":
        return empty

    for metric, value in parsed.get("metrics", {}).items():
        if metric not in METRICS:
            continue
        empty["metrics"][metric] = value
        empty["metric_sources"][metric] = "NSE Official Shareholding XBRL"
        empty["metric_urls"][metric] = filing_url
        empty["metric_periods"][metric] = period_end
        empty["metric_currencies"][metric] = ""
    return empty
