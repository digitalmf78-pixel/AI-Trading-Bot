"""Isolated ECMS EOD pipeline. Reads shared inputs; writes only outputs/ecms/."""
from __future__ import annotations

import argparse
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, time as datetime_time, timedelta
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
FILINGS_PATH = ROOT / "outputs/v8_official_financial_results_filings.csv"
EVIDENCE_PATH = ROOT / "data/inputs/fundamental_metric_verification_evidence.csv"
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

def expected_latest_completed_session(now: datetime | None = None) -> date:
    """Most recent NSE session whose cash-market EOD data should be complete."""
    local_now = now.astimezone(IST) if now and now.tzinfo else (now.replace(tzinfo=IST) if now else datetime.now(IST))
    day = local_now.date()
    if is_trading_session(day) and local_now.time() < datetime_time(16, 30):
        day -= timedelta(days=1)
    while not is_trading_session(day):
        day -= timedelta(days=1)
    return day

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
    latest_day, latest_path = max(valid, key=lambda item: item[0])
    expected_day = expected_latest_completed_session()
    if latest_day != expected_day:
        raise RuntimeError(
            f"WAIT_FOR_DATA: latest cached Bhavcopy is {latest_day}; "
            f"most recent completed NSE session should be {expected_day}"
        )
    return latest_day, latest_path

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
    # Match the repository's established listed-equity series allowlist.
    # Main Board membership is applied separately using official NSE lists.
    data = frame.copy()
    data["TckrSymb"] = data["TckrSymb"].astype(str).str.strip().str.upper()
    data["SctySrs"] = data["SctySrs"].astype(str).str.strip().str.upper()
    data["TtlTradgVol"] = pd.to_numeric(data["TtlTradgVol"], errors="coerce")
    data["ClsPric"] = pd.to_numeric(data["ClsPric"], errors="coerce")
    if "ISIN" in data.columns:
        isin = data["ISIN"].fillna("").astype(str).str.strip().str.upper()
        data = data[~isin.str.startswith("INF")]
    if "FinInstrmNm" in data.columns:
        names = data["FinInstrmNm"].fillna("").astype(str)
        data = data[~names.str.contains(r"\bAMC\s*-\s*", case=False, regex=True, na=False)]
    data = data[data["SctySrs"].isin({"EQ", "BE", "SM", "ST", "SZ"})]
    data = data[data["TckrSymb"].ne("") & data["TckrSymb"].ne("NAN") &
                data["TtlTradgVol"].gt(0) & data["ClsPric"].gt(0)]
    return data.drop_duplicates("TckrSymb", keep="first")

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
    """Load fresh official NSE Main Board and SME lists using the shared validated fetcher.

    The shared helper downloads the official NSE CSVs, validates their symbol
    columns, and persists the raw lists plus fetched_at timestamps for later
    read-only consumers. A fresh cache is used only when the live fetch fails.
    """
    from main_board_filter import load_official_board_lists

    main_symbols, sme_symbols, sources = load_official_board_lists()
    symbols = main_symbols - sme_symbols
    if not symbols:
        raise RuntimeError("WAIT_FOR_DATA: official Main Board list is empty after SME exclusion")
    return symbols, (
        f"NSE_MAIN={sources['main_board_source']};"
        f"NSE_SME={sources['sme_source']};"
        f"main_count={len(main_symbols)};sme_count={len(sme_symbols)}"
    )

def assess_fundamentals(candidates: pd.DataFrame, eod_date: date) -> pd.DataFrame:
    required = (METRICS_PATH, THRESHOLDS_PATH, FILINGS_PATH, EVIDENCE_PATH)
    if not all(path.exists() for path in required):
        out = candidates.copy()
        out["FundamentalShortlistStatus"] = "WAIT_FOR_DATA"
        out["FundamentalShortlistReason"] = "FUNDAMENTAL_METRICS_THRESHOLDS_OFFICIAL_FILINGS_OR_EVIDENCE_LEDGER_MISSING"
        return out
    metrics = pd.read_csv(METRICS_PATH)
    filings = pd.read_csv(FILINGS_PATH)
    evidence = pd.read_csv(EVIDENCE_PATH, keep_default_na=False)
    # Verify only candidate symbols against already cached official evidence.
    # This path never invokes XBRL downloads and never writes to shared data.
    metrics["TckrSymb"] = metrics["TckrSymb"].astype(str).str.strip().str.upper()
    duplicate_symbols = set(metrics.loc[metrics["TckrSymb"].duplicated(keep=False), "TckrSymb"])
    metrics_unique = metrics.drop_duplicates("TckrSymb", keep="first").copy()
    candidate_symbols = set(candidates["TckrSymb"].astype(str).str.upper())
    metrics_for_verification = metrics_unique[metrics_unique["TckrSymb"].isin(candidate_symbols)]
    filings_for_verification = filings[
        filings["TckrSymb"].astype(str).str.upper().isin(candidate_symbols)
    ] if "TckrSymb" in filings.columns else filings.iloc[0:0]
    evidence_for_verification = evidence[
        evidence["TckrSymb"].astype(str).str.upper().isin(candidate_symbols)
    ] if "TckrSymb" in evidence.columns else evidence.iloc[0:0]
    from fundamental_metric_verification import build_metric_verification
    verification, verification_summary, filing_summary = build_metric_verification(
        metrics_for_verification, filings_for_verification, evidence_for_verification, repo_root=ROOT
    )
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    verification.to_csv(OUTPUT_DIR / "fundamental_metric_verification.csv", index=False)
    verification_summary.to_csv(OUTPUT_DIR / "fundamental_metric_verification_summary.csv", index=False)
    filing_summary.to_csv(OUTPUT_DIR / "fundamental_filing_metadata_summary.csv", index=False)
    # Never refresh or mutate the shared metrics, filing register, evidence ledger or XML cache.
    joined = candidates.merge(metrics_unique, on="TckrSymb", how="left", suffixes=("", "_fundamental"))
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

def classify_catalyst(headline: str) -> tuple[str, str]:
    """Conservative headline triage; never treats a headline as confirmed financial impact."""
    text = str(headline or "").lower()
    negative_terms = (
        "fraud", "default", "insolvency", "nclt", "sebi penalty", "penalty imposed",
        "order cancelled", "contract terminated", "auditor resign", "auditor resignation",
        "rating downgraded", "rating downgrade", "plant shutdown", "fire at", "investigation",
        "show cause", "litigation", "winding up", "loan default", "pledge increased",
        "going concern", "qualified opinion", "regulatory action", "ban on",
    )
    positive_terms = (
        "work order", "purchase order", "letter of award", "letter of intent",
        "contract worth", "contract awarded", "order worth", "received an order",
        "bagged order", "project awarded", "commercial production", "commissioned",
        "regulatory approval", "drug approval", "capacity expansion", "new plant",
        "acquisition completed", "acquisition of", "merger approved", "joint venture",
        "strategic partnership", "capex", "profit jumped", "profit rises",
        "revenue rises", "revenue growth", "ebitda rises", "margin expansion",
    )
    risks = [term for term in negative_terms if term in text]
    positives = [term for term in positive_terms if term in text]
    if risks:
        return "NEGATIVE_RISK_REVIEW", "|".join(risks)
    if positives:
        return "STRONG_POSITIVE_CATALYST_REVIEW", "|".join(positives)
    return "NEWS_FOUND_NO_STRONG_CATALYST", ""

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
        strong_count = 0
        negative_count = 0
        for row in rows:
            signal, flags = classify_catalyst(row.get("Headline", ""))
            row["CatalystSignalStatus"] = signal
            row["RiskFlags"] = flags
            strong_count += signal == "STRONG_POSITIVE_CATALYST_REVIEW"
            negative_count += signal == "NEGATIVE_RISK_REVIEW"
        all_rows.extend(rows)
        if official_status != "AVAILABLE":
            status = "WAIT_FOR_DATA"
        elif official:
            status = "CATALYST_FOUND"
        elif secondary_status != "AVAILABLE":
            status = "WAIT_FOR_DATA"
        elif secondary:
            status = "CATALYST_FOUND_SECONDARY_ONLY"
        else:
            status = "NO_NEWS_FOUND"
        signal_status = ("NEGATIVE_RISK_REVIEW" if negative_count else
                         "STRONG_POSITIVE_CATALYST_REVIEW" if strong_count else
                         "NEWS_FOUND_NO_STRONG_CATALYST" if rows else "NO_CATALYST")
        audit.append({
            "TckrSymb": symbol, "NewsWindowStart": start.isoformat(),
            "NewsWindowEnd": eod_date.isoformat(), "OfficialStatus": official_status,
            "SecondaryStatus": secondary_status, "CatalystStatus": status,
            "CatalystSignalStatus": signal_status,
            "StrongCatalystCount": strong_count, "NegativeRiskCount": negative_count,
            "OfficialCount": len(official), "SecondaryCount": len(secondary),
        })
    news_columns = ["TckrSymb", "PublishedDate", "Headline", "Source", "SourceType",
                    "URL", "Impact", "CatalystSignalStatus", "RiskFlags"]
    audit_columns = ["TckrSymb", "NewsWindowStart", "NewsWindowEnd", "OfficialStatus",
                     "SecondaryStatus", "CatalystStatus", "CatalystSignalStatus",
                     "StrongCatalystCount", "NegativeRiskCount", "OfficialCount", "SecondaryCount"]
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
    board_universe_audit = volume.copy()
    mainboard_audit = board_universe_audit[board_universe_audit["MainBoardStatus"] == "PASS_MAIN_BOARD"].copy()
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
        lambda r: "NEGATIVE_RISK_REVIEW" if
        pd.to_numeric(r.get("NegativeRiskCount", 0), errors="coerce") > 0
        else ("EOD_RESEARCH_SHORTLIST" if
              str(r.get("FundamentalShortlistStatus", "")).upper() == "PASS"
              and str(r.get("CatalystStatus", "")).upper() in {"CATALYST_FOUND", "CATALYST_FOUND_SECONDARY_ONLY"}
              and str(r.get("CatalystSignalStatus", "")).upper() == "STRONG_POSITIVE_CATALYST_REVIEW"
              else ("WAIT_FOR_DATA" if
                    str(r.get("FundamentalShortlistStatus", "")).upper() == "WAIT_FOR_DATA"
                    or str(r.get("CatalystStatus", "")).upper() == "WAIT_FOR_DATA"
                    else "NOT_QUALIFIED")), axis=1)
    fundamentals = fundamentals.sort_values(["EODCandidateStatus", "RVOL"], ascending=[True, False])
    fundamentals.to_csv(OUTPUT_DIR / "eod_candidates.csv", index=False)
    audit = board_universe_audit.merge(
        fundamentals.drop(columns=[c for c in board_universe_audit.columns if c in fundamentals.columns and c != "TckrSymb"]),
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
