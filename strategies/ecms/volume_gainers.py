"""NSE Volume Gainers page scanner for ECMS. No orders; shared inputs are read-only."""
from __future__ import annotations
import argparse, json, os, re, shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
import requests
from strategies.ecms.eod import (
    IST, HEADERS, OUTPUT_DIR, METRICS_PATH, THRESHOLDS_PATH, FILINGS_PATH, EVIDENCE_PATH,
    expected_latest_completed_session,
    collect_catalysts, load_official_mainboard_symbols,
    discover_latest_session, load_prior_sessions, _read_valid_bhavcopy, calculate_rvol,
)
from fundamental_metric_verification import run_audit as run_fundamental_xbrl_audit
from fundamental_shortlist import build_fundamental_shortlist
from strategies.ecms.fundamental_research import assess_fundamental_research
from nse_trading_calendar import is_trading_session
NSE_PAGE = "https://www.nseindia.in/market-data/volume-gainers-spurts"
NSE_API = "https://www.nseindia.in/api/live-analysis-volume-gainers"
STATE_DIR = Path("data/cache/ecms")
STATE_FILE = STATE_DIR / "volume_gainers_previous_eod.csv"
REQUEST_TIMEOUT = (8, 20)
ALIASES = {
 "symbol": ("symbol","tradingSymbol","ticker"),
 "company": ("securityName","companyName","company","name"),
 "series": ("series","securitySeries"),
 "volume": ("volume","totalTradedVolume","totalTradedQty","tradedVolume","quantity"),
 "ltp": ("ltp","lastPrice","lastTradedPrice","closePrice"),
 "change_pct": ("pChange","perChange","changePercent","percentChange"),
 "turnover": ("turnover","totalTradedValue","value"),
 "avg_volume_1w": ("avgVolume1W","averageVolume1W","weekAvgVolume","avgVolume"),
 "change_times_1w": ("change1W","volumeChange1W","changeInVolume1W"),
 "avg_volume_2w": ("avgVolume2W","averageVolume2W","twoWeekAvgVolume","averageVolume"),
 "change_times_2w": ("change2W","volumeChange2W","changeInVolume2W"),
 "updated_at": ("updatedAt","updated_at","timestamp"),
}
def _key(value):
    return re.sub(r"[^a-z0-9]", "", str(value).lower())
def _find_records(payload):
    if isinstance(payload, list):
        rows = [x for x in payload if isinstance(x, dict)]
        if rows and any(_key(k) in {"symbol","tradingsymbol","ticker"} for r in rows for k in r):
            return rows
        for item in payload:
            found = _find_records(item)
            if found: return found
    elif isinstance(payload, dict):
        for name in ("data","volumeGainers","records","rows","tableData","result"):
            if name in payload:
                found = _find_records(payload[name])
                if found: return found
        for value in payload.values():
            found = _find_records(value)
            if found: return found
    return []
def _get(row, aliases):
    normalized = {_key(k): v for k,v in row.items()}
    for alias in aliases:
        if _key(alias) in normalized: return normalized[_key(alias)]
    return None
def _number(value):
    if value is None or str(value).strip() in {"","-","NA","None"}: return None
    try: return float(str(value).replace(",","").replace("%","").strip())
    except (TypeError,ValueError): return None
def fetch_volume_gainers(session=None):
    client = session or requests.Session()
    client.headers.update(HEADERS)
    client.headers["Referer"] = NSE_PAGE
    landing = client.get(NSE_PAGE, timeout=REQUEST_TIMEOUT); landing.raise_for_status()
    response = client.get(NSE_API, timeout=REQUEST_TIMEOUT); response.raise_for_status()
    rows = _find_records(response.json())
    if not rows: raise RuntimeError("WAIT_FOR_DATA: NSE Volume Gainers API returned no recognizable symbol rows")
    normalized=[]
    for row in rows:
        symbol=str(_get(row,ALIASES["symbol"]) or "").strip().upper()
        if not symbol or symbol in {"-","NAN","NONE"}: continue
        normalized.append({
          "TckrSymb":symbol, "CompanyName":str(_get(row,ALIASES["company"]) or ""),
          "Series":str(_get(row,ALIASES["series"]) or "").strip().upper(),
          "PageVolume":_number(_get(row,ALIASES["volume"])), "LTP":_number(_get(row,ALIASES["ltp"])),
          "ChangePct":_number(_get(row,ALIASES["change_pct"])), "Turnover":_number(_get(row,ALIASES["turnover"])),
          "AvgVolume1W":_number(_get(row,ALIASES["avg_volume_1w"])),
          "VolumeChangeTimes1W":_number(_get(row,ALIASES["change_times_1w"])),
          "AvgVolume2W":_number(_get(row,ALIASES["avg_volume_2w"])),
          "VolumeChangeTimes2W":_number(_get(row,ALIASES["change_times_2w"])),
          "NSEUpdatedAt":str(_get(row,ALIASES["updated_at"]) or ""),
        })
    frame=pd.DataFrame(normalized)
    if frame.empty: raise RuntimeError("WAIT_FOR_DATA: NSE response contained no valid symbols")
    return frame.drop_duplicates("TckrSymb",keep="first")
def _eligible_page_equities(page):
    mainboard, source=load_official_mainboard_symbols()
    eligible=page[page["TckrSymb"].isin(mainboard)].copy()
    eligible["PageUniverseStatus"]="PASS_MAIN_BOARD_EQUITY"
    return eligible,source
def assess_page_fundamentals(candidates, eod_date):
    """Collect and verify fundamentals for Volume Gainers candidates only.

    Reuses the repository's tested fundamental_data_provider and XBRL verifier,
    but runs them inside an ECMS-only workspace so production caches/reports are
    never modified by this shadow scanner.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ecms_output_dir = OUTPUT_DIR.resolve()
    candidate_symbols = set(candidates["TckrSymb"].astype(str).str.strip().str.upper())
    workspace = (STATE_DIR / "fundamental_workspace").resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    workspace_metrics = workspace / "data" / "inputs" / "fundamental_metrics.csv"
    workspace_filings = workspace / "outputs" / "v8_official_financial_results_filings.csv"
    workspace_evidence = workspace / "data" / "inputs" / "fundamental_metric_verification_evidence.csv"
    workspace_metrics.parent.mkdir(parents=True, exist_ok=True)
    workspace_filings.parent.mkdir(parents=True, exist_ok=True)
    workspace_evidence.parent.mkdir(parents=True, exist_ok=True)

    # Seed only the current Volume Gainers symbols from the shared read-only cache.
    # Once ECMS has its own cache, keep it as the source for subsequent EOD runs.
    if not workspace_metrics.exists() and METRICS_PATH.exists():
        shared = pd.read_csv(METRICS_PATH)
        if "TckrSymb" not in shared.columns:
            raise RuntimeError("Shared fundamental cache has no TckrSymb column")
        shared["TckrSymb"] = shared["TckrSymb"].astype(str).str.strip().str.upper()
        shared = shared[shared["TckrSymb"].isin(candidate_symbols)].copy()
        shared.to_csv(workspace_metrics, index=False)

    # Reuse official filing/evidence rows for these symbols only; the collector
    # refreshes missing filing metadata inside the isolated workspace.
    if not workspace_filings.exists() and FILINGS_PATH.exists():
        filings = pd.read_csv(FILINGS_PATH)
        if "TckrSymb" in filings.columns:
            filings["TckrSymb"] = filings["TckrSymb"].astype(str).str.strip().str.upper()
            filings = filings[filings["TckrSymb"].isin(candidate_symbols)].copy()
        filings.to_csv(workspace_filings, index=False)
    if not workspace_evidence.exists() and EVIDENCE_PATH.exists():
        evidence = pd.read_csv(EVIDENCE_PATH, keep_default_na=False)
        if "TckrSymb" in evidence.columns:
            evidence["TckrSymb"] = evidence["TckrSymb"].astype(str).str.strip().str.upper()
            evidence = evidence[evidence["TckrSymb"].isin(candidate_symbols)].copy()
        evidence.to_csv(workspace_evidence, index=False)

    repo_root = Path.cwd().resolve()
    ephemeral_root = (ecms_output_dir / "xbrl_ephemeral" / eod_date.isoformat()).resolve()
    if ephemeral_root.exists():
        shutil.rmtree(ephemeral_root)
    ephemeral_root.mkdir(parents=True, exist_ok=True)

    try:
        # Relative paths used by the production collector now resolve beneath
        # data/cache/ecms/fundamental_workspace, not production data/inputs/outputs.
        os.chdir(workspace)
        from fundamental_data_provider import collect_missing_fundamentals
        from strategies.ecms.free_fundamental_sources import fetch_ecms_free_fundamental_sources
        collect_missing_fundamentals(
            candidates,
            metrics_path=Path("data/inputs/fundamental_metrics.csv"),
            enabled=True,
            asof_date=eod_date,
            free_source_fetcher=fetch_ecms_free_fundamental_sources,
            force_retry_incomplete=True,
        )
    except Exception as exc:
        failed = candidates.copy()
        failed["FundamentalShortlistStatus"] = "WAIT_FOR_DATA"
        failed["FundamentalShortlistReason"] = (
            f"FUNDAMENTAL_COLLECTION_ERROR:{type(exc).__name__}:{str(exc)[:300]}"
        )
        failed["FundamentalAssessmentStatus"] = failed["FundamentalShortlistStatus"]
        failed["FundamentalAssessmentReason"] = failed["FundamentalShortlistReason"]
        failed["FundamentalResearchClassification"] = "INSUFFICIENT_DATA"
        failed["FundamentalResearchScore"] = pd.NA
        failed["FundamentalResearchCoveragePct"] = 0.0
        failed["FundamentalResearchProvenanceStatus"] = "NO_ELIGIBLE_METRICS"
        failed["StrongFundamentalHandOffStatus"] = "NOT_FORWARDED"
        failed["StrongFundamentalNotForwardedReason"] = "FUNDAMENTAL_COLLECTION_ERROR"
        pd.DataFrame([{
            "Status": "FUNDAMENTAL_COLLECTION_ERROR",
            "Reason": f"{type(exc).__name__}: {str(exc)[:500]}",
        }]).to_csv(ecms_output_dir / "fundamental_collection_error.csv", index=False)
        return failed
    finally:
        os.chdir(repo_root)

    if not workspace_metrics.exists():
        raise RuntimeError("Fundamental provider completed without creating its ECMS metrics cache")

    # Copy only prior evidence XMLs referenced by the candidate ledger into an
    # ephemeral root. New XBRL downloads are also written there by run_audit.
    if workspace_evidence.exists():
        evidence = pd.read_csv(workspace_evidence, keep_default_na=False)
        if "EvidenceFilePath" in evidence.columns:
            for raw_path in evidence["EvidenceFilePath"].dropna().astype(str).unique():
                if not raw_path.strip():
                    continue
                source = (repo_root / raw_path).resolve()
                try:
                    source.relative_to(repo_root)
                except ValueError:
                    continue
                if source.is_file():
                    destination = ephemeral_root / raw_path
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)

    metrics = pd.read_csv(workspace_metrics)
    if "TckrSymb" not in metrics.columns:
        raise RuntimeError("ECMS fundamental cache has no TckrSymb column")
    metrics["TckrSymb"] = metrics["TckrSymb"].astype(str).str.strip().str.upper()
    duplicate_symbols = set(metrics.loc[metrics["TckrSymb"].duplicated(keep=False), "TckrSymb"])
    metrics_unique = metrics.drop_duplicates("TckrSymb", keep="first").copy()

    verification = pd.DataFrame()
    try:
        verification, verification_summary, filing_summary = run_fundamental_xbrl_audit(
            metrics_path=workspace_metrics,
            filings_path=workspace_filings,
            evidence_path=workspace_evidence,
            output_dir=ecms_output_dir,
            repo_root=ephemeral_root,
            symbols=candidate_symbols,
        )
        verification_summary.to_csv(ecms_output_dir / "fundamental_metric_verification_summary.csv", index=False)
        filing_summary.to_csv(ecms_output_dir / "fundamental_filing_metadata_summary.csv", index=False)
    except Exception as exc:
        pd.DataFrame([{
            "Status": "XBRL_AUDIT_WAIT_FOR_DATA",
            "Reason": f"{type(exc).__name__}: {str(exc)[:500]}",
        }]).to_csv(ecms_output_dir / "fundamental_xbrl_audit_error.csv", index=False)

    candidate_verification = verification[
        verification["TckrSymb"].astype(str).str.upper().isin(candidate_symbols)
    ] if "TckrSymb" in verification.columns else verification.iloc[0:0]
    joined = candidates.merge(metrics_unique, on="TckrSymb", how="left", suffixes=("", "_fundamental"))
    assessed = build_fundamental_shortlist(
        joined, eod_date.isoformat(), write=False,
        metric_verification=candidate_verification,
        require_explicit_thresholds=True,
        thresholds_path=THRESHOLDS_PATH.resolve(),
    )
    # Independent research scoring uses available provider metrics; official XBRL
    # verification remains a separate status and the strict shortlist stays intact.
    assessed = assess_fundamental_research(assessed, candidate_verification)
    expected_symbols = candidates["TckrSymb"].astype(str).str.strip().str.upper().tolist()
    actual_symbols = assessed["TckrSymb"].astype(str).str.strip().str.upper().tolist()
    if len(actual_symbols) != len(expected_symbols) or set(actual_symbols) != set(expected_symbols) or len(actual_symbols) != len(set(actual_symbols)):
        raise RuntimeError(
            "ECMS_ASSESSMENT_INTEGRITY_ERROR: candidate and assessment row/symbol sets differ"
        )
    duplicated = assessed["TckrSymb"].astype(str).str.upper().isin(duplicate_symbols)
    assessed.loc[duplicated, "FundamentalShortlistStatus"] = "WAIT_FOR_DATA"
    assessed.loc[duplicated, "FundamentalShortlistReason"] = "DUPLICATE_FUNDAMENTAL_CACHE_ROWS"
    assessed.loc[duplicated, "FundamentalAssessmentStatus"] = assessed.loc[duplicated, "FundamentalShortlistStatus"]
    assessed.loc[duplicated, "FundamentalAssessmentReason"] = assessed.loc[duplicated, "FundamentalShortlistReason"]
    strong_mask = (
        assessed["FundamentalShortlistStatus"].astype(str).str.upper().eq("PASS")
        & assessed["FundamentalResearchClassification"].astype(str).str.upper().eq("STRONG")
        & pd.to_numeric(assessed["FundamentalResearchCoveragePct"], errors="coerce").ge(80)
    )
    assessed["StrongFundamentalHandOffStatus"] = strong_mask.map({
        True: "PASS_STRONG_FUNDAMENTAL", False: "NOT_FORWARDED"
    })
    assessed["StrongFundamentalNotForwardedReason"] = assessed.apply(
        lambda row: "" if bool(strong_mask.loc[row.name]) else
        "STRICT_SHORTLIST_" + str(row.get("FundamentalShortlistStatus", "MISSING")).upper()
        if str(row.get("FundamentalShortlistStatus", "")).upper() != "PASS" else
        "RESEARCH_" + str(row.get("FundamentalResearchClassification", "MISSING")).upper(),
        axis=1,
    )

    # Publish ECMS-owned copies for the workflow artifact; production files remain untouched.
    for source, name in [
        (workspace_metrics, "fundamental_metrics_ecms.csv"),
        (workspace_filings, "fundamental_filings_ecms.csv"),
        (workspace_evidence, "fundamental_evidence_ecms.csv"),
        (workspace / "outputs" / "v8_fundamental_provider_diagnostics.csv", "fundamental_provider_diagnostics.csv"),
    ]:
        if source.exists():
            shutil.copy2(source, ecms_output_dir / name)
    return assessed

def attach_page_rvol(candidates, eod_date):
    """Attach the repository's 20-session Bhavcopy RVOL without changing page membership."""
    result = candidates.copy()
    try:
        latest, latest_path = discover_latest_session()
        if latest != eod_date:
            raise RuntimeError(f"Bhavcopy latest session {latest} does not match page EOD date {eod_date}")
        history = load_prior_sessions(latest)
        current = _read_valid_bhavcopy(latest_path, latest)
        rvol = calculate_rvol(current, [frame for _, frame in history])
        rvol = rvol[rvol["TckrSymb"].astype(str).str.upper().isin(
            set(result["TckrSymb"].astype(str).str.upper())
        )][["TckrSymb", "AvgVolume20D", "RVOL", "VolumeScreenStatus"]]
        result = result.merge(rvol, on="TckrSymb", how="left", validate="one_to_one")
        result["RVOLDataStatus"] = result["VolumeScreenStatus"].fillna("WAIT_FOR_DATA")
    except Exception as exc:
        result["AvgVolume20D"] = pd.NA
        result["RVOL"] = pd.NA
        result["VolumeScreenStatus"] = "WAIT_FOR_DATA"
        result["RVOLDataStatus"] = f"WAIT_FOR_DATA:{type(exc).__name__}:{str(exc)[:180]}"
    return result

def run_eod():
    page=fetch_volume_gainers()
    eligible,board_source=_eligible_page_equities(page)
    if eligible.empty: raise RuntimeError("WAIT_FOR_DATA: no official Main Board equity symbols found on NSE Volume Gainers page")
    # Manual runs may be started on weekends/holidays. The NSE Volume Gainers
    # page then represents the most recently completed cash-market session.
    # Tag research with that official session date instead of rejecting today's
    # calendar date when today is not a trading day.
    eod_date=expected_latest_completed_session()
    if not is_trading_session(eod_date):
        raise RuntimeError(f"WAIT_FOR_DATA: resolved EOD date {eod_date} is not an official NSE equity trading session")
    eligible["EODDate"]=eod_date.isoformat(); eligible["PageSource"]=NSE_PAGE
    eligible["MainBoardSource"]=board_source
    eligible=attach_page_rvol(eligible,eod_date)
    assessed=assess_page_fundamentals(eligible,eod_date)
    assessed["EODConfirmationLabel"] = assessed["StrongFundamentalHandOffStatus"].map({
      "PASS_STRONG_FUNDAMENTAL":"STRONG_EOD", "NOT_FORWARDED":"NOT_STRONG_EOD"
    }).fillna("NOT_STRONG_EOD")
    news,news_audit=collect_catalysts(assessed,eod_date)
    assessed=assessed.merge(news_audit,on="TckrSymb",how="left")
    if (len(assessed) != len(eligible)
            or set(assessed["TckrSymb"].astype(str).str.upper()) != set(eligible["TckrSymb"].astype(str).str.upper())
            or assessed["TckrSymb"].astype(str).str.upper().duplicated().any()):
        raise RuntimeError("ECMS_EOD_REPORT_INTEGRITY_ERROR: joined report differs from eligible page candidates")
    if "NegativeRiskCount" not in assessed: assessed["NegativeRiskCount"]=0
    assessed["NegativeRiskCount"]=pd.to_numeric(assessed["NegativeRiskCount"],errors="coerce").fillna(0)
    assessed["EODResearchStatus"]=assessed.apply(
      lambda r: "NEGATIVE_RISK_REVIEW" if r["NegativeRiskCount"]>0 else
      ("STRONG_FUNDAMENTAL_CATALYST_REVIEW" if
       str(r.get("FundamentalShortlistStatus","")).upper()=="PASS" and
       str(r.get("CatalystSignalStatus","")).upper()=="STRONG_POSITIVE_CATALYST_REVIEW" and
       str(r.get("CatalystStatus","")).upper()=="CATALYST_FOUND" else
       ("WAIT_FOR_DATA" if str(r.get("FundamentalShortlistStatus","")).upper()=="WAIT_FOR_DATA" or
        str(r.get("CatalystStatus","")).upper()=="WAIT_FOR_DATA" else "NOT_QUALIFIED")),axis=1)
    sort_col="RVOL" if "RVOL" in assessed.columns else "PageVolume"
    assessed=assessed.sort_values(["EODResearchStatus",sort_col],ascending=[True,False])
    OUTPUT_DIR.mkdir(parents=True,exist_ok=True)
    assessed.to_csv(OUTPUT_DIR/"volume_gainers_eod_research.csv",index=False)
    page.to_csv(OUTPUT_DIR/"volume_gainers_page_raw.csv",index=False)
    news.to_csv(OUTPUT_DIR/"volume_gainers_catalysts.csv",index=False)
    STATE_DIR.mkdir(parents=True,exist_ok=True)
    state_columns=["TckrSymb","CompanyName","PageVolume","LTP","ChangePct","AvgVolume1W",
      "VolumeChangeTimes1W","AvgVolume2W","VolumeChangeTimes2W","EODDate"]
    for column in ("FundamentalShortlistStatus","FundamentalResearchClassification",
                   "FundamentalResearchScore","FundamentalResearchCoveragePct",
                   "FundamentalResearchProvenanceStatus","StrongFundamentalNotForwardedReason"):
        if column in assessed.columns:
            state_columns.append(column)
    state=assessed[state_columns].copy()
    state=state.rename(columns={
      "FundamentalShortlistStatus":"EODFundamentalShortlistStatus",
      "FundamentalResearchClassification":"EODFundamentalResearchClassification",
      "FundamentalResearchScore":"EODFundamentalResearchScore",
      "FundamentalResearchCoveragePct":"EODFundamentalResearchCoveragePct",
      "FundamentalResearchProvenanceStatus":"EODFundamentalResearchProvenanceStatus",
      "StrongFundamentalNotForwardedReason":"EODFundamentalNotForwardedReason"})
    state["EODStrongFundamentalStatus"]=state.apply(
      lambda r: "STRONG_EOD" if
        str(r.get("EODFundamentalShortlistStatus","")).upper()=="PASS" and
        str(r.get("EODFundamentalResearchClassification","")).upper()=="STRONG" and
        _number(r.get("EODFundamentalResearchCoveragePct")) is not None and
        float(r.get("EODFundamentalResearchCoveragePct"))>=80 else "NOT_STRONG_EOD",axis=1)
    state.to_csv(STATE_FILE,index=False)
    summary={"status":"PASS","eod_date_ist":eod_date.isoformat(),"nse_page":NSE_PAGE,
      "page_rows":int(len(page)),"eligible_mainboard_equities":int(len(eligible)),
      "strong_fundamental_handoff":int(assessed["StrongFundamentalHandOffStatus"].eq("PASS_STRONG_FUNDAMENTAL").sum()),
      "strong_eod":int(assessed["EODConfirmationLabel"].eq("STRONG_EOD").sum()),
      "strong_fundamental_catalyst_review":int(assessed["EODResearchStatus"].eq("STRONG_FUNDAMENTAL_CATALYST_REVIEW").sum()),
      "wait_for_data":int(assessed["EODResearchStatus"].eq("WAIT_FOR_DATA").sum()),
      "page_limit_note":"Processes every row returned by NSE page; page currently labels table Top 25.",
      "generated_at_ist":datetime.now(IST).isoformat(),"state_file":str(STATE_FILE)}
    (OUTPUT_DIR/"volume_gainers_eod_summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2)); return summary
def _strong_fundamental_mask(frame):
    if frame.empty:
        return pd.Series(False, index=frame.index)
    shortlist = frame.get("FundamentalShortlistStatus", pd.Series("", index=frame.index)).astype(str).str.upper()
    classification = frame.get("FundamentalResearchClassification", pd.Series("", index=frame.index)).astype(str).str.upper()
    coverage = pd.to_numeric(frame.get("FundamentalResearchCoveragePct", pd.Series(pd.NA, index=frame.index)), errors="coerce")
    return shortlist.eq("PASS") & classification.eq("STRONG") & coverage.ge(80)


def _confirmation_status(eod_strong, present, morning_strong):
    if eod_strong and present and morning_strong:
        return "DOUBLE_CONFIRMED_EOD_MORNING"
    if morning_strong:
        return "UNDER_OBSERVATION_MORNING"
    if eod_strong and present:
        return "EOD_STRONG_MORNING_NOT_CONFIRMED"
    if eod_strong and not present:
        return "STRONG_EOD_DISAPPEARED_MORNING"
    return "NOT_STRONG"


def run_morning():
    today = datetime.now(IST).date()
    if not is_trading_session(today):
        raise RuntimeError(f"WAIT_FOR_DATA: {today} is not an official NSE equity trading session")
    if not STATE_FILE.exists(): raise RuntimeError("WAIT_FOR_DATA: previous EOD Volume Gainers snapshot missing from ECMS state cache")
    previous=pd.read_csv(STATE_FILE,dtype={"TckrSymb":str})
    if previous.empty or "TckrSymb" not in previous: raise RuntimeError("WAIT_FOR_DATA: previous EOD snapshot empty or invalid")
    expected_eod = expected_latest_completed_session().isoformat()
    stored_dates = set(previous.get("EODDate", pd.Series(dtype=str)).dropna().astype(str))
    if stored_dates != {expected_eod}:
        raise RuntimeError(f"WAIT_FOR_DATA: cached EOD page snapshot dates {sorted(stored_dates)} do not match latest completed NSE session {expected_eod}")
    live=fetch_volume_gainers()
    mainboard,board_source=load_official_mainboard_symbols()
    live=live[live["TckrSymb"].isin(mainboard)].copy()
    if live.empty:
        raise RuntimeError("WAIT_FOR_DATA: no eligible Main Board candidates on 09:20 Volume Gainers page")

    # Run the same fundamental framework on every eligible symbol visible now,
    # including repeated EOD symbols and new morning entries. The collector
    # reuses complete ECMS cache rows and retries incomplete rows under ECMS policy.
    live["EODDate"]=expected_eod
    live["MorningDate"]=today.isoformat()
    live["MainBoardSource"]=board_source
    morning_assessed=assess_page_fundamentals(live,today)
    if "FundamentalShortlistStatus" not in morning_assessed:
        morning_assessed["FundamentalShortlistStatus"]="WAIT_FOR_DATA"
    if "FundamentalResearchClassification" not in morning_assessed:
        morning_assessed["FundamentalResearchClassification"]="INSUFFICIENT_DATA"
    morning_assessed["MorningStrongFundamentalStatus"] = (
        _strong_fundamental_mask(morning_assessed).map({True:"STRONG_MORNING",False:"NOT_STRONG_MORNING"})
    )

    previous_symbols=set(previous["TckrSymb"].astype(str).str.upper())
    live_symbols=set(live["TckrSymb"].astype(str).str.upper())
    live_by_symbol=live.set_index("TckrSymb",drop=False)
    morning_by_symbol=morning_assessed.set_index("TckrSymb",drop=False)
    previous_by_symbol=previous.set_index("TckrSymb",drop=False)
    rows=[]
    all_symbols=sorted(previous_symbols | live_symbols)
    for symbol in all_symbols:
        old=previous_by_symbol.loc[symbol].to_dict() if symbol in previous_by_symbol.index else {}
        current=live_by_symbol.loc[symbol].to_dict() if symbol in live_by_symbol.index else {}
        assessed=morning_by_symbol.loc[symbol].to_dict() if symbol in morning_by_symbol.index else {}
        present=symbol in live_symbols
        eod_strong=str(old.get("EODStrongFundamentalStatus","")).upper()=="STRONG_EOD"
        morning_strong=str(assessed.get("MorningStrongFundamentalStatus","")).upper()=="STRONG_MORNING"
        confirmation=_confirmation_status(eod_strong,present,morning_strong)
        rows.append({
          "TckrSymb":symbol,
          "CompanyName":current.get("CompanyName",old.get("CompanyName","")),
          "EODDate":old.get("EODDate",""),
          "MorningDate":today.isoformat(),
          "MorningStatus":"REPEATED" if symbol in previous_symbols and present else
             "DISAPPEARED" if symbol in previous_symbols else "NEW_ENTRY",
          "EODPageVolume":old.get("PageVolume"),
          "MorningPageVolume":current.get("PageVolume"),
          "EODLTP":old.get("LTP"),"MorningLTP":current.get("LTP"),
          "EODFundamentalShortlistStatus":old.get("EODFundamentalShortlistStatus",""),
          "EODFundamentalResearchClassification":old.get("EODFundamentalResearchClassification",""),
          "EODFundamentalResearchScore":old.get("EODFundamentalResearchScore"),
          "EODFundamentalResearchCoveragePct":old.get("EODFundamentalResearchCoveragePct"),
          "EODStrongFundamentalStatus":old.get("EODStrongFundamentalStatus",""),
          "EODFundamentalNotForwardedReason":old.get("EODFundamentalNotForwardedReason",""),
          "MorningFundamentalShortlistStatus":assessed.get("FundamentalShortlistStatus",""),
          "MorningFundamentalResearchClassification":assessed.get("FundamentalResearchClassification",""),
          "MorningFundamentalResearchScore":assessed.get("FundamentalResearchScore"),
          "MorningFundamentalResearchCoveragePct":assessed.get("FundamentalResearchCoveragePct"),
          "MorningFundamentalNotForwardedReason":assessed.get("StrongFundamentalNotForwardedReason",""),
          "MorningStrongFundamentalStatus":assessed.get("MorningStrongFundamentalStatus","NOT_ASSESSED"),
          "ConfirmationStatus":confirmation,
          "MorningChangePct":current.get("ChangePct"),
          "MorningVolumeChangeTimes1W":current.get("VolumeChangeTimes1W"),
          "MorningVolumeChangeTimes2W":current.get("VolumeChangeTimes2W"),
          "DataQuality":"LIVE_PAGE_AND_FUNDAMENTALS" if present and assessed else
            "NOT_ON_CURRENT_PAGE" if not present else "PARTIAL_LIVE_DATA"})
    report=pd.DataFrame(rows)
    OUTPUT_DIR.mkdir(parents=True,exist_ok=True)
    report.to_csv(OUTPUT_DIR/"volume_gainers_morning_recheck.csv",index=False)
    # Preserve the original EOD snapshot; only the fundamental workspace cache
    # is enriched by the morning assessment.
    summary={"status":"PASS","morning_time_ist":datetime.now(IST).isoformat(),
      "previous_eod_symbols":len(previous_symbols),"current_page_eligible_symbols":len(live_symbols),
      "repeated":int(report["MorningStatus"].eq("REPEATED").sum()),
      "disappeared":int(report["MorningStatus"].eq("DISAPPEARED").sum()),
      "new_entries":int(report["MorningStatus"].eq("NEW_ENTRY").sum()),
      "morning_assessed_candidates":int(len(morning_assessed)),
      "morning_assessment_rows":int(report["MorningStrongFundamentalStatus"].ne("NOT_ASSESSED").sum()),
      "morning_strong":int(report["MorningStrongFundamentalStatus"].eq("STRONG_MORNING").sum()),
      "morning_wait_for_data":int(morning_assessed["FundamentalShortlistStatus"].astype(str).str.upper().eq("WAIT_FOR_DATA").sum()),
      "under_observation":int(report["ConfirmationStatus"].eq("UNDER_OBSERVATION_MORNING").sum()),
      "double_confirmed":int(report["ConfirmationStatus"].eq("DOUBLE_CONFIRMED_EOD_MORNING").sum()),
      "eod_strong_not_confirmed":int(report["ConfirmationStatus"].isin(
        ["EOD_STRONG_MORNING_NOT_CONFIRMED","STRONG_EOD_DISAPPEARED_MORNING"]).sum()),
      "nse_page":NSE_PAGE,
      "note":"Every eligible 09:20 page candidate receives the ECMS fundamental assessment. DOUBLE_CONFIRMED requires strict PASS and independent STRONG at both EOD and morning checkpoints."}
    (OUTPUT_DIR/"volume_gainers_morning_summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2)); return summary
def main():
    parser=argparse.ArgumentParser(description="ECMS NSE Volume Gainers scanner")
    parser.add_argument("--mode",choices=("eod","morning"),required=True)
    args=parser.parse_args()
    run_eod() if args.mode=="eod" else run_morning()
if __name__=="__main__": main()
