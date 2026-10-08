"""Collect official NSE filings and free news corroboration for V8 top-volume names.

The NSE RSS feeds are the primary source. Google News RSS is used only to find
secondary coverage. A headline is not treated as proof of why a stock moved.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
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


def _norm(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", _clean(value).upper()).strip()


def _published(item: ET.Element) -> datetime | None:
    raw = item.findtext("pubDate") or item.findtext("{http://purl.org/dc/elements/1.1/}date")
    if not raw:
        return None
    try:
        stamp = parsedate_to_datetime(raw)
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return stamp.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _source_domain(url: str) -> str:
    match = re.search(r"https?://([^/]+)", url or "", re.I)
    return (match.group(1).lower().removeprefix("www.") if match else "")


def _impact(headline: str) -> str:
    text = _norm(headline)
    negative = (
        "DEFAULT", "FRAUD", "INSOLVENCY", "BANKRUPTCY", "PENALTY",
        "FINES", "DOWNGRADE", "RESIGNS", "RESIGNATION", "ORDER CANCELLED",
        "CONTRACT TERMINATED", "PROBE", "INVESTIGATION", "LOSSES WIDEN",
        "PROFIT FALL", "PROFIT DECLINE", "REVENUE FALL", "REVENUE DECLINE",
        "PLEDGE INVOCATION", "AUDITOR RESIGNS", "REGULATORY ACTION",
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
        master = pd.read_csv(EQUITY_MASTER_CACHE)
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


def _rss_items(url: str, params: dict | None = None) -> list[ET.Element]:
    response = requests.get(url, params=params, headers=HEADERS, timeout=15)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    return list(root.findall("./channel/item"))


def collect_catalyst_news(result: pd.DataFrame, eod_date) -> tuple[pd.DataFrame, dict[str, str]]:
    """Return official NSE filings plus secondary headlines for RVOL top 20."""
    if result.empty or "TckrSymb" not in result.columns:
        return pd.DataFrame(columns=NEWS_COLUMNS), {"NSE": "no candidates", "secondary": "not checked"}

    candidates = result.copy()
    candidates["RVOL"] = pd.to_numeric(candidates.get("RVOL"), errors="coerce")
    candidates = candidates.sort_values("RVOL", ascending=False).head(20)
    symbols = {str(value).strip().upper() for value in candidates["TckrSymb"]}
    names = _read_equity_master()
    try:
        eod_day = pd.Timestamp(eod_date)
        eod_day = eod_day.tz_localize("Asia/Kolkata") if eod_day.tzinfo is None else eod_day.tz_convert("Asia/Kolkata")
        cutoff = (eod_day.normalize() - pd.Timedelta(days=5)).to_pydatetime().astimezone(timezone.utc)
    except Exception:
        cutoff = datetime.now(timezone.utc) - timedelta(days=5)
    rows: list[dict[str, str]] = []
    status = {"NSE": "available", "secondary": "available"}
    nse_successes = 0

    # Read each exchange feed once, then map company names/symbols to the Top 20.
    for feed_name, feed_url in NSE_FEEDS.items():
        try:
            items = _rss_items(feed_url)
        except Exception as exc:
            print(f"{feed_name} fetch failed: {exc}")
            continue
        nse_successes += 1
        for item in items:
            title = _clean(item.findtext("title", ""))
            description = _clean(item.findtext("description", ""))
            content = _norm(title + " " + description)
            stamp = _published(item)
            if stamp is None or stamp < cutoff:
                continue
            link = _clean(item.findtext("link", ""))
            for symbol in symbols:
                company = names.get(symbol, "")
                company_norm = _norm(company)
                symbol_match = bool(re.search(rf"(?<![A-Z0-9]){re.escape(symbol)}(?![A-Z0-9])", content))
                company_match = len(company_norm) >= 8 and company_norm in content
                if not (symbol_match or company_match):
                    continue
                rows.append({
                    "TckrSymb": symbol,
                    "PublishedAt": stamp.isoformat() if stamp else "",
                    "Headline": title or description,
                    "Source": "NSE India",
                    "SourceType": "primary",
                    "URL": link or "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
                    "Impact": _impact(title + " " + description),
                    "EventID": "",
                    "SourceDomain": _source_domain(link) or "archives.nseindia.com",
                })

    if nse_successes == 0:
        status["NSE"] = "unavailable"
    elif nse_successes < len(NSE_FEEDS):
        status["NSE"] = "partly available"

    # Free Google News RSS helps discover independent press coverage. It never
    # upgrades itself to primary evidence; the NSE file remains authoritative.
    secondary_successes = 0
    for symbol in sorted(symbols):
        try:
            query = f'"{symbol}" NSE India stock when:5d'
            items = _rss_items(GOOGLE_RSS_URL, {
                "q": query, "hl": "en-IN", "gl": "IN", "ceid": "IN:en",
            })
        except Exception as exc:
            print(f"Secondary news fetch failed for {symbol}: {exc}")
            continue
        secondary_successes += 1
        for item in items:
            title = _clean(item.findtext("title", ""))
            source_node = item.find("source")
            source_name = _clean(source_node.text if source_node is not None else "Google News")
            source_url = source_node.get("url", "") if source_node is not None else ""
            stamp = _published(item)
            if stamp is None or stamp < cutoff:
                continue
            # Exact ticker matching reduces false matches on short company names.
            if not re.search(rf"(?<![A-Z0-9]){re.escape(symbol)}(?![A-Z0-9])", _norm(title)):
                continue
            rows.append({
                "TckrSymb": symbol,
                "PublishedAt": stamp.isoformat() if stamp else "",
                "Headline": title,
                "Source": source_name or "बातमी स्रोत",
                "SourceType": "secondary",
                "URL": _clean(item.findtext("link", "")),
                "Impact": _impact(title),
                "EventID": "",
                "SourceDomain": _source_domain(source_url),
            })

    if secondary_successes == 0:
        status["secondary"] = "unavailable"
    elif secondary_successes < len(symbols):
        status["secondary"] = "partly available"

    frame = pd.DataFrame(rows, columns=NEWS_COLUMNS)
    if not frame.empty:
        frame = frame.drop_duplicates(
            subset=["TckrSymb", "Headline", "SourceDomain"], keep="first"
        )
    Path("data/inputs").mkdir(parents=True, exist_ok=True)
    frame.to_csv("data/inputs/news_evidence_auto.csv", index=False)
    print(f"Catalyst scan: {len(frame)} matched filing/news rows across {len(symbols)} top-volume symbols.")
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
    if result.empty:
        return ["आजच्या अहवालात शेअर्सची यादी उपलब्ध नाही."]
    candidates = result.copy()
    candidates["RVOL"] = pd.to_numeric(candidates.get("RVOL"), errors="coerce")
    candidates = candidates.sort_values("RVOL", ascending=False).head(20)
    market_close = _eod_market_close(eod_date)
    lines = [
        "एनएसई V8 — व्यवहारवाढ आणि कंपनी घडामोडी",
        f"तारीख: {eod_date}",
        "खालील २० शेअर्सची निवड जास्त सापेक्ष व्यवहारावरून झाली आहे.",
        "भाव-व्यवहाराचा नमुना हा संकेत आहे; तो बातमीमुळेच घडला याची खात्री नाही.",
        "ही माहिती अभ्यासासाठी आहे; कोणताही व्यवहार आपोआप होत नाही.",
        "",
    ]
    for number, (_, row) in enumerate(candidates.iterrows(), start=1):
        symbol = str(row.get("TckrSymb", "")).strip()
        try:
            rvol = float(row.get("RVOL"))
            rvol_text = f"{rvol:.2f} पट"
        except (TypeError, ValueError):
            rvol_text = "मोजता आला नाही"
        try:
            change = float(row.get("PriceChangePct"))
            change_text = f"{change:+.2f}%"
        except (TypeError, ValueError):
            change_text = "उपलब्ध नाही"
        matched = news[news["TckrSymb"].astype(str).str.upper() == symbol.upper()] if not news.empty else pd.DataFrame()
        official = matched[matched["SourceType"].astype(str).str.lower().isin({"primary", "official", "exchange", "company", "regulator"})] if not matched.empty else pd.DataFrame()
        secondary = matched[~matched.index.isin(official.index)] if not matched.empty else pd.DataFrame()
        chosen = official.iloc[0] if not official.empty else secondary.iloc[0] if not secondary.empty else None
        lines.append(f"{number}. {symbol} — भावबदल {change_text}; नेहमीच्या व्यवहाराच्या तुलनेत {rvol_text}.")
        volume_signal = str(row.get("VolumeReason", "WAIT_FOR_DATA"))
        volume_label = {
            "Demand-led": "खरेदीकडे झुकणारा नमुना",
            "Supply-led": "विक्रीकडे झुकणारा नमुना",
            "Balanced / unclear": "संतुलित किंवा अस्पष्ट नमुना",
            "No unusual volume": "विशेष व्यवहारवाढ नाही",
        }.get(volume_signal, "नमुना मोजता आला नाही")
        lines.append(f"   भाव-व्यवहार संकेत: {volume_label}; हा तांत्रिक अंदाज आहे, कारणाची पुष्टी नाही.")
        if chosen is None:
            if feed_status.get("NSE") != "available":
                lines.append(f"   NSE घोषणांची तपासणी पूर्ण झाली नाही ({feed_status.get('NSE')}); कारण अनिश्चित.")
            else:
                lines.append("   मागील ५ दिवसांत जुळणारी अधिकृत घोषणा सापडली नाही; कारण पुष्टी नाही.")
        else:
            headline = str(chosen.get("Headline", ""))
            source_type = str(chosen.get("SourceType", "")).lower()
            category = category_marathi(headline)
            impact = _event_impact_marathi(headline, str(chosen.get("Impact", "neutral")))
            if source_type in {"primary", "official", "exchange", "company", "regulator"}:
                verification = f"{chosen.get('Source', 'एक्स्चेंज')} वरील अधिकृत नोंद"
            else:
                verification = f"दुय्यम बातमी ({chosen.get('Source', 'स्रोत')}); अधिकृत पुष्टी नाही"
            lines.append(f"   जुळलेली घडामोड: {category}; {verification}.")
            lines.append(f"   प्राथमिक अर्थ: {impact}.")
            published = pd.to_datetime(chosen.get("PublishedAt", ""), errors="coerce", utc=True)
            if pd.notna(published) and published.tz_convert("Asia/Kolkata") > market_close:
                lines.append("   ही नोंद बाजार बंद झाल्यानंतर आली; आजच्या व्यवहाराचे कारण नाही, पुढील सत्रासाठी लक्षात घ्या.")
            lines.append(f"   मूळ दुवा: {chosen.get('URL', '')}")
        evidence_status = str(row.get("NewsEvidenceStatus", "NO_DATA"))
        if evidence_status == "CONFIRMED_3_PLUS_1":
            lines.append("   पुष्टी: अधिकृत नोंद आणि तीन स्वतंत्र बातमी-स्रोत आढळले.")
        elif evidence_status == "PRIMARY_CONFIRMED":
            lines.append("   पुष्टी: अधिकृत नोंद मिळाली; ३+१ स्वतंत्र पुष्टी पूर्ण नाही.")
        elif evidence_status == "UNVERIFIED":
            lines.append("   पुष्टी: दुय्यम बातमी आहे; अधिकृत नोंद सापडलेली नाही.")
        else:
            lines.append("   पुष्टी: आवश्यक अधिकृत नोंद मिळालेली नाही.")
        lines.append("")
    lines.append("टीप: घोषणा आणि व्यवहारातील वेळ जुळली तरी तीच भावबदलाची निश्चित कारणीभूत गोष्ट असेल असे सिद्ध होत नाही.")
    lines.append("स्रोत तपासणी — NSE घोषणा: " + ("उपलब्ध" if feed_status.get("NSE") == "available" else "अडचण") + "; इतर बातम्या: " + feed_status.get("secondary", "तपासल्या नाहीत") + ".")
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
