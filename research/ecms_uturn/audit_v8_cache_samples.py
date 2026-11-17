"""Audit existing shared NSE V8 cache for ECMS U-Turn research; read-only."""
from __future__ import annotations
import csv, json, re
from pathlib import Path
import pandas as pd
from strategies.ecms.uturn_nse_ohlc import extract_nse_eq_ohlc_row, build_nse_symbol_ohlc_window

ROOT=Path(".")
OUT=ROOT/"v8_cache_audit"
OUT.mkdir(exist_ok=True)
PEAK= list(csv.DictReader((ROOT/"research/ecms_uturn/nse_ohlc_download_manifest.csv").open(encoding="utf-8-sig")))
CLOSE=list(csv.DictReader((ROOT/"research/ecms_uturn/post_result_close_manifest.csv").open(encoding="utf-8-sig")))
symbols=sorted({r["Symbol"] for r in PEAK})
bhav_root=ROOT/"data/bhavcopy"
del_root=ROOT/"data/cache/delivery"

def date_tokens(path):
    s=path.stem
    found=set()
    for x in re.findall(r"(?<!\d)(20\d{6})(?!\d)",s):
        try: found.add(pd.to_datetime(x,format="%Y%m%d").date().isoformat())
        except Exception: pass
    for x in re.findall(r"(?<!\d)(\d{2})(\d{2})(20\d{2})(?!\d)",s):
        try: found.add(pd.to_datetime("".join(x),format="%d%m%Y").date().isoformat())
        except Exception: pass
    return found

def index_files(root, date_columns):
    """Index files by the session dates inside their tables, not filename guesses."""
    idx={}
    if root.exists():
        for p in root.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in {".csv",".zip"}:
                continue
            try:
                frame=load_table(p)
                norm={str(col).strip().lower():col for col in frame.columns}
                datecol=next((norm[name.lower()] for name in date_columns if name.lower() in norm),None)
                if not datecol:
                    continue
                dates=pd.to_datetime(frame[datecol],errors="coerce",dayfirst=False).dt.date.astype("string")
                for day in sorted(set(dates.dropna().tolist())):
                    idx.setdefault(day,[]).append(p)
            except Exception:
                continue
    return idx

def load_table(path):
    if path.suffix.lower()==".zip":
        import zipfile
        with zipfile.ZipFile(path) as z:
            names=[n for n in z.namelist() if n.lower().endswith(".csv")]
            if len(names)!=1: raise ValueError(f"ZIP CSV count={len(names)}")
            with z.open(names[0]) as f: return pd.read_csv(f,dtype=str)
    return pd.read_csv(path,dtype=str,encoding="utf-8-sig")

def find_date_col(df, candidates):
    norm={str(c).strip().lower():c for c in df.columns}
    for c in candidates:
        if c.lower() in norm: return norm[c.lower()]
    return None

bhav_idx=index_files(bhav_root,["TradDt","DATE1","Date"])
delivery_idx=index_files(del_root,["DATE1","DATE"])

def verify_bhav(symbol, session, path):
    df=load_table(path)
    datecol=find_date_col(df,["TradDt","DATE1","Date"])
    if not datecol: return {"status":"WAIT_FOR_DATA","reason":"No recognised session-date column","path":str(path)}
    dates=pd.to_datetime(df[datecol],errors="coerce",dayfirst=True).dt.date.astype("string")
    actual=dates.dropna().unique().tolist()
    if session not in actual: return {"status":"UNVERIFIED","reason":f"File date mismatch; expected {session}, row dates sample={actual[:3]}","path":str(path)}
    url=f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{session.replace('-','')}_F_0000.csv.zip"
    result=extract_nse_eq_ohlc_row(df,symbol=symbol,expected_session=session,source_url=url)
    result["CachePath"]=str(path)
    return result

ohlc_rows=[]; windows=[]; post_rows=[]; delivery_rows=[]; session_audit_rows=[]
for sym in symbols:
    expected=[r["Expected_NSE_Session"] for r in PEAK if r["Symbol"]==sym]
    records=[]; symbol_results=[]
    for day in expected:
        candidates=bhav_idx.get(day,[])
        if not candidates:
            symbol_results.append({"Symbol":sym,"Date":day,"Status":"WAIT_FOR_DATA","Reason":"No cached bhavcopy file for expected session"})
            continue
        ready=[]
        failures=[]
        for candidate in candidates:
            try:
                res=verify_bhav(sym,day,candidate)
                if res.get("status")=="READY":
                    ready.append((candidate,res))
                else:
                    failures.append(f"{candidate}:{res.get('status')}:{res.get('reason','')}")
            except Exception as e:
                failures.append(f"{candidate}:{type(e).__name__}:{e}")
        if len(ready)!=1:
            reason=("No candidate file contained one verified EQ row; "+" | ".join(failures[:5])) if not ready else f"Ambiguous: {len(ready)} candidate files each contain a valid row"
            symbol_results.append({"Symbol":sym,"Date":day,"Status":"WAIT_FOR_DATA","Reason":reason,"CachePaths":";".join(map(str,candidates))})
            continue
        chosen_path,res=ready[0]
        symbol_results.append({"Symbol":sym,"Date":day,"Status":"READY","Reason":"","High":res.get("High"),"Close":res.get("Close"),"ISIN":res.get("ISIN"),"CachePath":str(chosen_path)})
        ohlc_rows.append(res)
        records.append({"session_date":day,"source_url":f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{day.replace('-','')}_F_0000.csv.zip","bhavcopy":load_table(chosen_path)})
    # The parser requires complete 20-row coverage; feed only successful dated records.
    result=build_nse_symbol_ohlc_window(records,symbol=sym,expected_sessions=expected,announcement_date=next(r["Result_Announcement_Date"] for r in PEAK if r["Symbol"]==sym),window_sessions=20)
    peak_date=""; peak_high=""
    if result.get("status")=="READY":
        peak_frame=result["ohlc"].copy()
        peak_frame["High"]=pd.to_numeric(peak_frame["High"],errors="coerce")
        peak_row=peak_frame.loc[peak_frame["High"].idxmax()]
        peak_date=str(peak_row["Date"]); peak_high=float(peak_row["High"])
    windows.append({"Symbol":sym,"ExpectedSessions":20,"VerifiedSessions":len(records),"Status":result["status"],"Reason":result["reason"],"WindowStart":result.get("window_start",""),"WindowEnd":result.get("window_end",""),"ISIN":result.get("ISIN",""),"PeakDate":peak_date,"PeakHigh":peak_high})
    for item in symbol_results:
        delivery_candidates=delivery_idx.get(item["Date"],[])
        if len(delivery_candidates)!=1:
            delivery_rows.append({"Symbol":sym,"Date":item["Date"],"Status":"WAIT_FOR_DATA","Reason":f"Expected one delivery file; found {len(delivery_candidates)}"})
            continue
        try:
            dd=load_table(delivery_candidates[0])
            norm={str(c).strip().upper():c for c in dd.columns}
            scol=norm.get("SYMBOL"); dcol=norm.get("DATE1") or norm.get("DATE")
            qcol=norm.get("DELIV_QTY"); pcol=norm.get("DELIV_PER")
            if not all([scol,dcol,qcol,pcol]):
                raise ValueError(f"Delivery columns missing; headers={list(dd.columns)}")
            ds=pd.to_datetime(dd[dcol],errors="coerce",dayfirst=True).dt.date.astype("string")
            ss=dd[dd[scol].astype(str).str.strip().str.upper().eq(sym) & ds.eq(item["Date"])]
            delivery_rows.append({"Symbol":sym,"Date":item["Date"],"Status":"READY" if len(ss)==1 else "WAIT_FOR_DATA","RowsFound":len(ss),"DeliveryQty":ss.iloc[0][qcol] if len(ss)==1 else "","DeliveryPct":ss.iloc[0][pcol] if len(ss)==1 else "","CachePath":str(delivery_candidates[0]),"Reason":"" if len(ss)==1 else "Expected exactly one symbol/date delivery row"})
        except Exception as e:
            delivery_rows.append({"Symbol":sym,"Date":item["Date"],"Status":"WAIT_FOR_DATA","Reason":f"{type(e).__name__}: {e}"})

for row in CLOSE:
    sym=row["Symbol"]; day=row["Latest_Completed_Post_Result_Session_AsOf_2026_11_17"]; cand=bhav_idx.get(day,[])
    if len(cand)!=1:
        post_rows.append({"Symbol":sym,"Date":day,"Status":"WAIT_FOR_DATA","Reason":f"Expected one cached bhavcopy file; found {len(cand)}"}); continue
    try:
        res=verify_bhav(sym,day,cand[0]); post_rows.append({"Symbol":sym,"Date":day,"Status":res.get("status"),"Close":res.get("Close"),"High":res.get("High"),"ISIN":res.get("ISIN"),"CachePath":str(cand[0]),"Reason":res.get("reason","")})
    except Exception as e: post_rows.append({"Symbol":sym,"Date":day,"Status":"WAIT_FOR_DATA","Reason":f"{type(e).__name__}: {e}"})

# EPS search is deliberately discovery-only: provider EPS columns are not proof of annual diluted EPS.
eps_hits=[]
search_roots=[ROOT/"data/inputs/fundamental_metrics.csv",ROOT/"data/cache/fundamental_history",ROOT/"data/cache/xbrl_samples",ROOT/"data/cache/xbrl_period_pairs",ROOT/"outputs/v8_official_financial_results_filings.csv"]
for base in search_roots:
    files=[base] if base.is_file() else list(base.rglob("*")) if base.exists() else []
    for p in files:
        if not p.is_file() or p.stat().st_size>20_000_000: continue
        if p.suffix.lower() not in {".csv",".json",".xml",".txt",".html"}: continue
        try:
            raw=p.read_text(encoding="utf-8-sig",errors="ignore")
            for sym in symbols:
                if sym not in raw.upper(): continue
                lines=[ln[:700] for ln in raw.splitlines() if sym in ln.upper() and re.search(r"dilut|eps|earnings.?per.?share",ln,re.I)]
                for ln in lines[:10]:
                    eps_hits.append({"Symbol":sym,"Path":str(p),"EvidenceClass":"DISCOVERY_ONLY_NOT_VERIFIED","LineExcerpt":ln})
        except Exception: pass
pd.DataFrame(ohlc_rows).to_csv(OUT/"cached_ohlc_verified_rows.csv",index=False)\npd.DataFrame(session_audit_rows).to_csv(OUT/"cached_ohlc_session_audit.csv",index=False)
pd.DataFrame(windows).to_csv(OUT/"cached_ohlc_window_summary.csv",index=False)
pd.DataFrame(post_rows).to_csv(OUT/"cached_post_result_close.csv",index=False)
pd.DataFrame(delivery_rows).to_csv(OUT/"cached_delivery_coverage.csv",index=False)
pd.DataFrame(eps_hits).to_csv(OUT/"diluted_eps_discovery_only.csv",index=False)
summary={"research_only":True,"cache_source":"restored shared NSE V8 cache; read-only","symbols":windows,"pre_result_rows_ready":len(ohlc_rows),"post_result_close_ready":sum(r.get("Status")=="READY" for r in post_rows),"delivery_rows_ready":sum(r.get("Status")=="READY" for r in delivery_rows),"delivery_rows_expected":len(delivery_rows),"eps_discovery_hits":len(eps_hits),"eps_verified":False,"corporate_action_review":"PENDING","uturn_target_calculation_performed":False}
(OUT/"symbol_audit_summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
print(json.dumps(summary,indent=2))
# A completed audit job can report partial coverage; statuses remain explicit and no target is computed.
