"""NSE Volume Gainers page scanner for ECMS. No orders; shared inputs are read-only."""
from __future__ import annotations
import argparse, json, re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
import requests
from strategies.ecms.eod import (
    IST, HEADERS, OUTPUT_DIR, assess_fundamentals, collect_catalysts,
    load_official_mainboard_symbols,
)
NSE_PAGE = "https://www.nseindia.in/market-data/volume-gainers-spurts"
NSE_API = "https://www.nseindia.com/api/live-analysis-volume-gainers"
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
def run_eod():
    page=fetch_volume_gainers()
    eligible,board_source=_eligible_page_equities(page)
    if eligible.empty: raise RuntimeError("WAIT_FOR_DATA: no official Main Board equity symbols found on NSE Volume Gainers page")
    today=datetime.now(IST).date()
    eligible["EODDate"]=today.isoformat(); eligible["PageSource"]=NSE_PAGE
    eligible["MainBoardSource"]=board_source
    assessed=assess_fundamentals(eligible,today)
    news,news_audit=collect_catalysts(assessed,today)
    assessed=assessed.merge(news_audit,on="TckrSymb",how="left")
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
    state=eligible[["TckrSymb","CompanyName","PageVolume","LTP","ChangePct","AvgVolume1W",
      "VolumeChangeTimes1W","AvgVolume2W","VolumeChangeTimes2W","EODDate"]].copy()
    state.to_csv(STATE_FILE,index=False)
    summary={"status":"PASS","eod_date_ist":today.isoformat(),"nse_page":NSE_PAGE,
      "page_rows":int(len(page)),"eligible_mainboard_equities":int(len(eligible)),
      "strong_fundamental_catalyst_review":int(assessed["EODResearchStatus"].eq("STRONG_FUNDAMENTAL_CATALYST_REVIEW").sum()),
      "wait_for_data":int(assessed["EODResearchStatus"].eq("WAIT_FOR_DATA").sum()),
      "page_limit_note":"Processes every row returned by NSE page; page currently labels table Top 25.",
      "generated_at_ist":datetime.now(IST).isoformat(),"state_file":str(STATE_FILE)}
    (OUTPUT_DIR/"volume_gainers_eod_summary.json").write_text(json.dumps(summary,indent=2)+"\\n",encoding="utf-8")
    print(json.dumps(summary,indent=2)); return summary
def run_morning():
    if not STATE_FILE.exists(): raise RuntimeError("WAIT_FOR_DATA: previous EOD Volume Gainers snapshot missing from ECMS state cache")
    previous=pd.read_csv(STATE_FILE,dtype={"TckrSymb":str})
    if previous.empty or "TckrSymb" not in previous: raise RuntimeError("WAIT_FOR_DATA: previous EOD snapshot empty or invalid")
    live=fetch_volume_gainers()
    mainboard,board_source=load_official_mainboard_symbols()
    live=live[live["TckrSymb"].isin(mainboard)].copy()
    previous_symbols=set(previous["TckrSymb"].astype(str).str.upper())
    live_symbols=set(live["TckrSymb"].astype(str).str.upper())
    live_by_symbol=live.set_index("TckrSymb",drop=False)
    rows=[]
    for _,old in previous.iterrows():
        symbol=str(old["TckrSymb"]).upper()
        current=live_by_symbol.loc[symbol].to_dict() if symbol in live_by_symbol.index else {}
        present=symbol in live_symbols
        rows.append({"TckrSymb":symbol,"CompanyName":old.get("CompanyName",""),
          "EODDate":old.get("EODDate",""),"MorningDate":datetime.now(IST).date().isoformat(),
          "MorningStatus":"REPEATED" if present else "DISAPPEARED",
          "EODPageVolume":old.get("PageVolume"),"MorningPageVolume":current.get("PageVolume"),
          "EODLTP":old.get("LTP"),"MorningLTP":current.get("LTP"),
          "MorningChangePct":current.get("ChangePct"),
          "MorningVolumeChangeTimes1W":current.get("VolumeChangeTimes1W"),
          "MorningVolumeChangeTimes2W":current.get("VolumeChangeTimes2W"),
          "DataQuality":"LIVE_PAGE_DATA" if present and current.get("PageVolume") is not None else
            ("PARTIAL_LIVE_DATA" if present else "NOT_ON_CURRENT_PAGE")})
    for symbol in sorted(live_symbols-previous_symbols):
        current=live_by_symbol.loc[symbol].to_dict()
        rows.append({"TckrSymb":symbol,"CompanyName":current.get("CompanyName",""),
          "EODDate":"","MorningDate":datetime.now(IST).date().isoformat(),"MorningStatus":"NEW_ENTRY",
          "EODPageVolume":None,"MorningPageVolume":current.get("PageVolume"),"EODLTP":None,
          "MorningLTP":current.get("LTP"),"MorningChangePct":current.get("ChangePct"),
          "MorningVolumeChangeTimes1W":current.get("VolumeChangeTimes1W"),
          "MorningVolumeChangeTimes2W":current.get("VolumeChangeTimes2W"),
          "DataQuality":"LIVE_PAGE_DATA" if current.get("PageVolume") is not None else "PARTIAL_LIVE_DATA"})
    report=pd.DataFrame(rows); report["MainBoardSource"]=board_source
    OUTPUT_DIR.mkdir(parents=True,exist_ok=True)
    report.to_csv(OUTPUT_DIR/"volume_gainers_morning_recheck.csv",index=False)
    summary={"status":"PASS","morning_time_ist":datetime.now(IST).isoformat(),
      "previous_eod_symbols":len(previous_symbols),"current_page_eligible_symbols":len(live_symbols),
      "repeated":int(report["MorningStatus"].eq("REPEATED").sum()),
      "disappeared":int(report["MorningStatus"].eq("DISAPPEARED").sum()),
      "new_entries":int(report["MorningStatus"].eq("NEW_ENTRY").sum()),"nse_page":NSE_PAGE,
      "note":"Snapshot at workflow execution time; not a full-day volume comparison."}
    (OUTPUT_DIR/"volume_gainers_morning_summary.json").write_text(json.dumps(summary,indent=2)+"\\n",encoding="utf-8")
    print(json.dumps(summary,indent=2)); return summary
def main():
    parser=argparse.ArgumentParser(description="ECMS NSE Volume Gainers scanner")
    parser.add_argument("--mode",choices=("eod","morning"),required=True)
    args=parser.parse_args()
    run_eod() if args.mode=="eod" else run_morning()
if __name__=="__main__": main()
