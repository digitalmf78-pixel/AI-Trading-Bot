"""Isolated ECMS EOD pipeline. Reads shared inputs; writes only outputs/ecms/."""
from __future__ import annotations

import argparse
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from nse_trading_calendar import CalendarCoverageError, is_trading_session
from fundamental_shortlist import build_fundamental_shortlist

ROOT = Path(".")
BHAVCOPY_DIR = ROOT / "data/bhavcopy"
UNIVERSE_DIR = ROOT / "data/cache/universe"
METRICS_PATH = ROOT / "data/inputs/fundamental_metrics.csv"
THRESHOLDS_PATH = ROOT / "data/inputs/fundamental_thresholds.json"
METRIC_VERIFICATION_PATH = ROOT / "outputs/v8_fundamental_metric_verification.csv"
OUTPUT_DIR = ROOT / "outputs/ecms"
LOOKBACK_SESSIONS = 20
MIN_RVOL = 1.5
NEWS_DAYS = 5
IST = ZoneInfo("Asia/Kolkata")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ECMS-research/1.0)",
    "Accept": "application/json,text/html,application/rss+xml,*/*",
    "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
}
REQUIRED_BHAVCOPY = {"TckrSymb", "SctySrs", "TtlTradgVol", "ClsPric", "BizDt"}
FUNDAMENTAL_REQUIRED = {
    "RevenueGrowthPct", "ProfitGrowthPct", "ROEPercent", "ROCEPercent",
    "DebtToEquity", "InterestCoverage", "OperatingCashFlowINR",
}

def _date_from_file(path: Path) -> date | None:
    match = re.fullmatch(r"bhavcopy_(\d{8})\.csv", path.name)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y%m%d").date()
    except ValueError:
        return None

def _read_valid_bhavcopy(path: Path, expected: date) -> pd.DataFrame:
    frame = pd.read_csv(path)
    missing = REQUIRED_BHAVCOPY - set(frame.columns)
    if missing:
        raise ValueError(f"{path.name}: missing columns {sorted(missing)}")
    if len(frame) < 500:
        raise ValueError(f"{path.name}: suspiciously incomplete Bhavcopy ({len(frame)} rows; expected at least 500)")
    raw_dates = pd.to_datetime(frame["BizDt"], errors="coerce").dt.date.dropna().unique()
    if set(raw_dates) != {expected}:
        raise ValueError(f"{path.name}: internal BizDt does not match filename/session {expected}")
    if not is_trading_session(expected):
        raise ValueError(f"{expected} is not an official NSE equity session")
    return frame

def discover_latest_session(bhavcopy_dir: Path = BHAVCOPY_DIR) -> tuple[date, Path]:
    if not bhavcopy_dir.exists():
        raise FileNotFoundError("Bhavcopy cache directory is missing")
    valid = []
    errors = []
    for path in bhavcopy_dir.glob("bhavcopy_????????.csv"):
        day = _date_from_file(path)
        if day is None:
            continue
        try:
            if is_trading_session(day):
                _read_valid_bhavcopy(path, day)
                valid.append((day, path))
        except CalendarCoverageError:
            raise
        except Exception as exc:
            errors.append(f"{path.name}:{exc}")
    if not valid:
        raise RuntimeError("WAIT_FOR_DATA: no valid latest complete Bhavcopy session; " + "; ".join(errors[:5]))
    return max(valid, key=lambda item: item[0])

def load_prior_sessions(latest: date, count: int = LOOKBACK_SESSIONS,
                        bhavcopy_dir: Path = BHAVCOPY_DIR) -> list[tuple[date, pd.DataFrame]]:
    found = []
    for path in bhavcopy_dir.glob("bhavcopy_????????.csv"):
        day = _date_from_file(path)
        if day is None or day >= latest:
            continue
        try:
            if is_trading_session(day):
                found.append((day, path))
        except CalendarCoverageError:
            raise
    found.sort(key=lambda item: item[0], reverse=True)
    result = []
    invalid = []
    for day, path in found:
        try:
            frame = _read_valid_bhavcopy(path, day)
        except Exception as exc:
            invalid.append(f"{path.name}:{exc}")
            continue
        result.append((day, frame))
        if len(result) == count:
            break
    if len(result) < count:
        raise RuntimeError(f"WAIT_FOR_DATA: need {count} prior complete sessions; found {len(result)}")
    return result

def _equity_rows(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    data["TckrSymb"] = data["TckrSymb"].astype(str).str.strip().str.upper()
    data["SctySrs"] = data["SctySrs"].astype(str).str.strip().str.upper()
    data["TtlTradgVol"] = pd.to_numeric(data["TtlTradgVol"], errors="coerce")
    data["ClsPric"] = pd.to_numeric(data["ClsPric"], errors="coerce")
    if "ISIN" in data.columns:
        isin = data["ISIN"].astype(str).str.upper()
        data = data[~isin.str.startswith("INF")]
    data = data[(data["SctySrs"] == "EQ") & data["TckrSymb"].ne("") &
                data["TckrSymb"].ne("NAN") & data["TtlTradgVol"].gt(0)]
    return data.drop_duplicates("TckrSymb", keep="last")

def calculate_rvol(current: pd.DataFrame, history: list[pd.DataFrame]) -> pd.DataFrame:
    """Current full-session volume divided by mean volume of prior complete sessions."""
    if len(history) < LOOKBACK_SESSIONS:
        raise ValueError(f"Need {LOOKBACK_SESSIONS} historical sessions, got {len(history)}")
    current_eq = _equity_rows(current)
    volumes = []
    for frame in history:
        clean = _equity_rows(frame)[["TckrSymb", "TtlTradgVol"]].rename(
            columns={"TtlTradgVol": f"vol_{len(volumes)}"})
        volumes.append(clean)
    baseline = volumes[0]
    for item in volumes[1:]:
        baseline = baseline.merge(item, on="TckrSymb", how="outer")
    vol_cols = [c for c in baseline.columns if c.startswith("vol_")]
    baseline["AvgVolume20D"] = baseline[vol_cols].mean(axis=1, skipna=False)
    result = current_eq.merge(baseline[["TckrSymb", "AvgVolume20D"]], on="TckrSymb", how="left")
    result["RVOL"] = result["TtlTradgVol"] / result["AvgVolume20D"]
    result["VolumeScreenStatus"] = result["RVOL"].map(
        lambda value: "PASS_RVOL_GE_1_5" if pd.notna(value) and value >= MIN_RVOL
        else ("WAIT_FOR_DATA" if pd.isna(value) else "BELOW_RVOL_THRESHOLD"))
    return result

def load_official_mainboard_symbols(universe_dir: Path = UNIVERSE_DIR) -> tuple[set[str], str]:
    """Use only a previously restored, timestamped official NSE Main Board list."""
    main = universe_dir / "nse_main_board_equity.csv"
    main_stamp = universe_dir / "nse_main_board_equity.fetched_at"
    sme = universe_dir / "nse_sme_equity.csv"
    sme_stamp = universe_dir / "nse_sme_equity.fetched_at"
    if not all(p.exists() for p in (main, main_stamp, sme, sme_stamp)):
        raise RuntimeError("WAIT_FOR_DATA: restored official Main Board/SME lists or timestamps missing")
    now = datetime.now(ZoneInfo("UTC"))
    ages = []
    for stamp in (main_stamp, sme_stamp):
        fetched = datetime.fromtimestamp(int(stamp.read_text().strip()), tz=ZoneInfo("UTC"))
        age = (now - fetched).total_seconds()
        if age < 0 or age > 7 * 86400:
            raise RuntimeError(f"WAIT_FOR_DATA: official board cache stale ({age/86400:.1f} days)")
        ages.append(age)
    main_frame = pd.read_csv(main, dtype=str)
    sme_frame = pd.read_csv(sme, dtype=str)
    main_col = next((c for c in main_frame.columns if str(c).strip().upper() == "SYMBOL"), None)
    sme_col = next((c for c in sme_frame.columns if str(c).strip().upper() == "SYMBOL"), None)
    if not main_col or not sme_col:
        raise RuntimeError("WAIT_FOR_DATA: official board CSV has no SYMBOL column")
    main_symbols = {str(x).strip().upper() for x in main_frame[main_col].dropna()
                    if str(x).strip() and str(x).strip().lower() != "nan"}
    sme_symbols = {str(x).strip().upper() for x in sme_frame[sme_col].dropna()
                   if str(x).strip() and str(x).strip().lower() != "nan"}
    symbols = main_symbols - sme_symbols
    if not symbols:
        raise RuntimeError("WAIT_FOR_DATA: official Main Board list is empty after SME exclusion")
    return symbols, f"NSE_EQUITY_L+SME_CACHE age_hours={max(ages)/3600:.1f}"

def assess_fundamentals(candidates: pd.DataFrame, eod_date: date) -> pd.DataFrame:
    if not METRICS_PATH.exists() or not THRESHOLDS_PATH.exists() or not METRIC_VERIFICATION_PATH.exists():
        out = candidates.copy()
        out["FundamentalShortlistStatus"] = "WAIT_FOR_DATA"
        out["FundamentalShortlistReason"] = "FUNDAMENTAL_METRICS_OR_EXPLICIT_THRESHOLDS_OR_XBRL_VERIFICATION_MISSING"
        return out
    metrics = pd.read_csv(METRICS_PATH)
    verification = pd.read_csv(METRIC_VERIFICATION_PATH)
    # Never refresh the shared metrics cache from this isolated workflow.
    metrics["TckrSymb"] = metrics["TckrSymb"].astype(str).str.strip().str.upper()
    duplicate_symbols = set(metrics.loc[metrics["TckrSymb"].duplicated(keep=False), "TckrSymb"])
    joined = candidates.merge(metrics, on="TckrSymb", how="left", suffixes=("", "_fundamental"))
    assessed = build_fundamental_shortlist(
        joined, eod_date.isoformat(), write=False,
        metric_verification=verification, require_explicit_thresholds=True,
        thresholds_path=THRESHOLDS_PATH,
    )
    duplicated = assessed["TckrSymb"].astype(str).str.upper().isin(duplicate_symbols)
    assessed.loc[duplicated, "FundamentalShortlistStatus"] = "WAIT_FOR_DATA"
    assessed.loc[duplicated, "FundamentalShortlistReason"] = "DUPLICATE_FUNDAMENTAL_CACHE_ROWS"
    return assessed

def _exact_issuer_match(text: str, symbol: str, company: str = "") -> bool:
    upper = str(text or "").upper()
    if re.search(rf"(?<![A-Z0-9]){re.escape(symbol.upper())}(?![A-Z0-9])", upper):
        return True
    return bool(company and company.strip().upper() in upper)

def fetch_official_announcements(symbol: str, start: date, end: date,
                                 session: requests.Session | None = None) -> tuple[list[dict], str]:
    client = session or requests.Session()
    client.headers.update(HEADERS)
    try:
        landing = client.get("https://www.nseindia.com/companies-listing/corporate-filings-announcements", timeout=(5, 12))
        landing.raise_for_status()
        response = client.get(
            "https://www.nseindia.com/api/corporate-announcements",
            params={"index": "equities", "symbol": symbol, "from_date": start.strftime("%d-%m-%Y"),
                    "to_date": end.strftime("%d-%m-%Y")},
            timeout=(5, 15),
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            return [], "WAIT_FOR_DATA:UNEXPECTED_NSE_PAYLOAD"
        rows = []
        for item in payload:
            if not isinstance(item, dict) or str(item.get("symbol", "")).strip().upper() != symbol.upper():
                continue
            raw_date = item.get("an_dt") or item.get("sort_date") or item.get("dt")
            stamp = pd.to_datetime(raw_date, errors="coerce", dayfirst=True)
            if pd.isna(stamp):
                continue
            if stamp.tzinfo is not None:
                published = stamp.tz_convert(IST).date()
            else:
                published = stamp.date()
            if not start <= published <= end:
                continue
            rows.append({
                "TckrSymb": symbol, "PublishedDate": published.isoformat(),
                "Headline": str(item.get("desc") or item.get("subject") or item.get("attchmntText") or ""),
                "Source": "NSE", "SourceType": "OFFICIAL",
                "URL": str(item.get("attchmntFile") or ""),
                "Impact": "REVIEW_REQUIRED",
            })
        return rows, "AVAILABLE"
    except Exception as exc:
        return [], f"WAIT_FOR_DATA:{type(exc).__name__}:{str(exc)[:180]}"

def fetch_secondary_news(symbol: str, company: str, start: date, end: date,
                         session: requests.Session | None = None) -> tuple[list[dict], str]:
    client = session or requests.Session()
    try:
        query = requests.utils.quote(f'"{company or symbol}" NSE stock')
        url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
        response = client.get(url, headers=HEADERS, timeout=(5, 12))
        response.raise_for_status()
        root = ET.fromstring(response.content)
        rows = []
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub = pd.to_datetime(item.findtext("pubDate"), errors="coerce", utc=True)
            if pd.isna(pub):
                continue
            day = pub.tz_convert(IST).date()
            if not start <= day <= end or not _exact_issuer_match(title, symbol, company):
                continue
            rows.append({
                "TckrSymb": symbol, "PublishedDate": day.isoformat(),
                "Headline": title, "Source": "Google News RSS",
                "SourceType": "SECONDARY_UNVERIFIED", "URL": link,
                "Impact": "REVIEW_REQUIRED",
            })
        return rows, "AVAILABLE"
    except Exception as exc:
        return [], f"WAIT_FOR_DATA:{type(exc).__name__}:{str(exc)[:180]}"

def collect_catalysts(candidates: pd.DataFrame, eod_date: date,
                      official_fetcher=fetch_official_announcements,
                      secondary_fetcher=fetch_secondary_news) -> tuple[pd.DataFrame, pd.DataFrame]:
    start = eod_date - timedelta(days=NEWS_DAYS - 1)
    all_rows, audit = [], []
    names = {}
    if (UNIVERSE_DIR / "nse_main_board_equity.csv").exists():
        try:
            master = pd.read_csv(UNIVERSE_DIR / "nse_main_board_equity.csv", dtype=str)
            sym = next(c for c in master.columns if c.strip().upper() == "SYMBOL")
            name = next(c for c in master.columns if "NAME OF COMPANY" in c.strip().upper())
            names = dict(zip(master[sym].astype(str).str.upper(), master[name].astype(str)))
        except Exception:
            names = {}
    for symbol in candidates["TckrSymb"].astype(str).str.upper().drop_duplicates():
        company = names.get(symbol, "")
        official, official_status = official_fetcher(symbol, start, eod_date)
        secondary, secondary_status = secondary_fetcher(symbol, company, start, eod_date)
        rows = official + secondary
        all_rows.extend(rows)
        status = ("CATALYST_FOUND" if rows else
                  "NO_NEWS_FOUND" if official_status == "AVAILABLE" and secondary_status == "AVAILABLE"
                  else "WAIT_FOR_DATA")
        audit.append({
            "TckrSymb": symbol, "NewsWindowStart": start.isoformat(),
            "NewsWindowEnd": eod_date.isoformat(), "OfficialStatus": official_status,
            "SecondaryStatus": secondary_status, "CatalystStatus": status,
            "OfficialCount": len(official), "SecondaryCount": len(secondary),
        })
    news_columns = ["TckrSymb", "PublishedDate", "Headline", "Source", "SourceType", "URL", "Impact"]
    audit_columns = ["TckrSymb", "NewsWindowStart", "NewsWindowEnd", "OfficialStatus",
                     "SecondaryStatus", "CatalystStatus", "OfficialCount", "SecondaryCount"]
    return pd.DataFrame(all_rows, columns=news_columns), pd.DataFrame(audit, columns=audit_columns)

def run_eod(eod_date: date | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    latest, latest_path = discover_latest_session()
    if eod_date and latest != eod_date:
        raise RuntimeError(f"Requested EOD date {eod_date} but latest valid Bhavcopy is {latest}")
    history = load_prior_sessions(latest)
    current = _read_valid_bhavcopy(latest_path, latest)
    volume = calculate_rvol(current, [frame for _, frame in history])
    mainboard, board_source = load_official_mainboard_symbols()
    volume["MainBoardStatus"] = volume["TckrSymb"].map(
        lambda s: "PASS_MAIN_BOARD" if s in mainboard else "EXCLUDED_NOT_IN_OFFICIAL_MAIN_BOARD")
    mainboard_audit = volume[volume["MainBoardStatus"] == "PASS_MAIN_BOARD"].copy()
    candidates = mainboard_audit[mainboard_audit["VolumeScreenStatus"] == "PASS_RVOL_GE_1_5"].copy()
    candidates["EODDate"] = latest.isoformat()
    candidates["MainBoardSource"] = board_source
    fundamentals = assess_fundamentals(candidates, latest)
    news, news_audit = collect_catalysts(fundamentals, latest)
    if not news.empty:
        counts = news.groupby("TckrSymb").size().rename("CatalystRows")
        fundamentals = fundamentals.merge(counts, on="TckrSymb", how="left")
    else:
        fundamentals["CatalystRows"] = 0
    fundamentals = fundamentals.merge(news_audit, on="TckrSymb", how="left")
    fundamentals["EODCandidateStatus"] = fundamentals.apply(
        lambda r: "EOD_RESEARCH_SHORTLIST" if
        str(r.get("FundamentalShortlistStatus", "")).upper() == "PASS"
        and str(r.get("CatalystStatus", "")).upper() == "CATALYST_FOUND"
        else ("WAIT_FOR_DATA" if
              str(r.get("FundamentalShortlistStatus", "")).upper() == "WAIT_FOR_DATA"
              or str(r.get("CatalystStatus", "")).upper() == "WAIT_FOR_DATA"
              else "NOT_QUALIFIED"), axis=1)
    fundamentals = fundamentals.sort_values(["EODCandidateStatus", "RVOL"], ascending=[True, False])
    fundamentals.to_csv(OUTPUT_DIR / "eod_candidates.csv", index=False)
    audit = mainboard_audit.merge(
        fundamentals.drop(columns=[c for c in mainboard_audit.columns if c in fundamentals.columns and c != "TckrSymb"]),
        on="TckrSymb", how="left", suffixes=("", "_ecms"))
    audit.to_csv(OUTPUT_DIR / "eod_audit.csv", index=False)
    news.to_csv(OUTPUT_DIR / "eod_catalysts.csv", index=False)
    summary = {
        "status": "PASS", "eod_date": latest.isoformat(),
        "bhavcopy_file": str(latest_path), "prior_sessions_used": len(history),
        "mainboard_symbols": len(mainboard), "rvol_candidates": len(candidates),
        "research_shortlist": int(fundamentals["EODCandidateStatus"].eq("EOD_RESEARCH_SHORTLIST").sum()),
        "wait_for_data": int(fundamentals["EODCandidateStatus"].eq("WAIT_FOR_DATA").sum()),
        "rvol_threshold": MIN_RVOL, "rvol_lookback_sessions": LOOKBACK_SESSIONS,
        "catalyst_window_calendar_days": NEWS_DAYS,
        "generated_at_ist": datetime.now(IST).isoformat(),
    }
    (OUTPUT_DIR / "eod_run_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return fundamentals, news

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--eod-date", help="Optional ISO date; must equal latest valid cached Bhavcopy session")
    args = parser.parse_args()
    day = date.fromisoformat(args.eod_date) if args.eod_date else None
    run_eod(day)

if __name__ == "__main__":
    main()
