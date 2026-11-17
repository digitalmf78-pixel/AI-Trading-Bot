"""Isolated U-Turn historical event-study on restored NSE V8 cache (read-only).

Formula validation only: no entries, exits, position sizing, orders or trading signals.
Price outcomes are provisional until corporate-action comparability is audited.
"""
from __future__ import annotations
import csv, json, zipfile
from pathlib import Path
import pandas as pd

ROOT=Path("."); CACHE=ROOT/"data/bhavcopy"; OUT=ROOT/"uturn_cache_backtest"
OUT.mkdir(exist_ok=True)
EVENTS=ROOT/"research/ecms_uturn/backtest_events.csv"
MANIFEST=ROOT/"research/ecms_uturn/nse_ohlc_download_manifest.csv"
REQUIRED={"TradDt","Sgmt","FinInstrmTp","TckrSymb","SctySrs","HghPric","LwPric","ClsPric","TtlTradgVol","ISIN"}
EXPECTED_ISIN={"INFY":"INE009A01021","ACI":"INE128X01021","AARTIIND":"INE769A01020"}

def read_frame(path):
    if path.suffix.lower()==".zip":
        with zipfile.ZipFile(path) as z:
            names=[n for n in z.namelist() if n.lower().endswith(".csv")]
            if len(names)!=1: raise ValueError(f"ZIP CSV count={len(names)}")
            with z.open(names[0]) as f: return pd.read_csv(f,dtype=str)
    return pd.read_csv(path,dtype=str,encoding="utf-8-sig")

def load_prices(symbols):
    frames=[]; errors=[]
    files=sorted(p for p in CACHE.rglob("*") if p.is_file() and p.suffix.lower() in {".csv",".zip"}) if CACHE.exists() else []
    for path in files:
        try:
            df=read_frame(path)
            if not REQUIRED.issubset(df.columns): continue
            dates=pd.to_datetime(df["TradDt"],errors="coerce").dt.date.astype("string").dropna().unique().tolist()
            if len(dates)!=1:
                errors.append({"Path":str(path),"Reason":f"TRADDT_NOT_SINGLE_SESSION:{dates[:3]}"}); continue
            day=dates[0]
            df=df[(df["TradDt"].notna())
                & df["Sgmt"].astype(str).str.upper().eq("CM")
                & df["FinInstrmTp"].astype(str).str.upper().eq("STK")
                & df["SctySrs"].astype(str).str.upper().eq("EQ")
                & df["TckrSymb"].astype(str).str.upper().isin(symbols)].copy()
            if df.empty: continue
            df["Date"]=day
            for dest,src in [("High","HghPric"),("Low","LwPric"),("Close","ClsPric"),("Volume","TtlTradgVol")]:
                df[dest]=pd.to_numeric(df[src],errors="coerce")
            df["TckrSymb"]=df["TckrSymb"].astype(str).str.upper().str.strip()
            df["ISIN"]=df["ISIN"].astype(str).str.strip().str.upper()
            df["CachePath"]=str(path)
            frames.append(df[["TckrSymb","Date","High","Low","Close","Volume","ISIN","CachePath"]])
        except Exception as exc: errors.append({"Path":str(path),"Reason":f"{type(exc).__name__}:{exc}"})
    return (pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()),files,errors

def main():
    events=list(csv.DictReader(EVENTS.open(encoding="utf-8-sig",newline="")))
    manifest=list(csv.DictReader(MANIFEST.open(encoding="utf-8-sig",newline="")))
    symbols={r["Symbol"].upper() for r in events}
    prices,files,errors=load_prices(symbols)
    results=[]; horizons=[]; windows=[]
    for ev in events:
        sym=ev["Symbol"].upper(); event=pd.Timestamp(ev["Result_Announcement_Date"]).date().isoformat()
        prior=float(ev["Previous_FY_Diluted_EPS_INR"]); current=float(ev["Current_FY_Diluted_EPS_INR"])
        s=prices[prices["TckrSymb"].eq(sym)].copy() if not prices.empty else pd.DataFrame()
        if s.empty:
            results.append({"Symbol":sym,"Status":"WAIT_FOR_DATA","Reason":"NO_CACHED_SYMBOL_ROWS"}); continue
        s=s.sort_values("Date")
        if s["Date"].duplicated().any():
            results.append({"Symbol":sym,"Status":"WAIT_FOR_DATA","Reason":"DUPLICATE_SYMBOL_SESSION_ROWS"}); continue
        if set(s["ISIN"].unique())!={EXPECTED_ISIN[sym]}:
            results.append({"Symbol":sym,"Status":"WAIT_FOR_DATA","Reason":f"ISIN_MISMATCH:{sorted(s['ISIN'].unique())}"}); continue
        bad=s[["High","Low","Close","Volume"]].isna().any(axis=1) | (s["High"]<=0) | (s["Low"]<=0) | (s["Close"]<=0) | (s["Volume"]<0) | (s["High"]<s["Low"]) | (s["Close"]>s["High"]) | (s["Close"]<s["Low"])
        if bad.any():
            results.append({"Symbol":sym,"Status":"WAIT_FOR_DATA","Reason":f"INVALID_OHLCV_ROWS:{int(bad.sum())}"}); continue
        expected=[r["Expected_NSE_Session"] for r in manifest if r["Symbol"].upper()==sym]
        pre=s[s["Date"].isin(expected)].copy()
        missing=sorted(set(expected)-set(pre["Date"].tolist()))
        if len(expected)!=20 or len(pre)!=20 or missing:
            results.append({"Symbol":sym,"Status":"WAIT_FOR_DATA","Reason":f"PRE_WINDOW_INCOMPLETE expected={len(expected)} verified={len(pre)} missing={missing}"}); continue
        if any(d>=event for d in pre["Date"].tolist()):
            results.append({"Symbol":sym,"Status":"WAIT_FOR_DATA","Reason":"ANNOUNCEMENT_DATE_LEAKAGE"}); continue
        peakrow=pre.loc[pre["High"].idxmax()]; peak=float(peakrow["High"])
        post=s[s["Date"]>event].sort_values("Date")
        if post.empty:
            results.append({"Symbol":sym,"Status":"WAIT_FOR_DATA","Reason":"NO_POST_RESULT_SESSIONS"}); continue
        first=post.iloc[0]; last=post.iloc[-1]; first_close=float(first["Close"])
        eps_status="EPS_DECLINE" if current<prior else "NO_EPS_DECLINE"
        target=peak*current/prior if eps_status=="EPS_DECLINE" and prior>0 and current>0 else None
        hits=post[post["Low"]<=target] if target is not None else pd.DataFrame()
        hit=hits.iloc[0] if not hits.empty else None
        results.append({
            "Symbol":sym,"Status":"PROVISIONAL_EVENT_STUDY","EPSStatus":eps_status,
            "PreviousDilutedEPS":prior,"CurrentDilutedEPS":current,"ReportingBasis":ev["Reporting_Basis"],
            "PreResultSessionsVerified":len(pre),"PeakHigh":peak,"PeakHighDate":str(peakrow["Date"]),
            "FirstPostResultSession":str(first["Date"]),"FirstPostResultClose":first_close,
            "LatestPostResultSession":str(last["Date"]),"LatestPostResultClose":float(last["Close"]),
            "UturnEstimateProvisional":target,"TargetTouchedByDailyLow":bool(hit is not None) if target is not None else "",
            "FirstTargetTouchDate":str(hit["Date"]) if hit is not None else "",
            "BarsToFirstTouch":int(post.index.get_loc(hit.name)+1) if hit is not None else "",
            "LatestCloseVsTargetPct":(float(last["Close"])/target-1)*100 if target else "",
            "CorporateActionStatus":"NOT_AUDITED_PROVISIONAL","Interpretation":"EVENT_STUDY_ONLY_NO_ENTRY_EXIT_OR_PNL",
            "PeakCachePath":str(peakrow["CachePath"]),"LatestCachePath":str(last["CachePath"]),
            "EPSAnnualReportURL":ev["Official_Annual_Report_URL"],"ResultFilingURL":ev["Official_Result_Filing_URL"],
        })
        windows.append({"Symbol":sym,"ExpectedSessions":20,"VerifiedSessions":len(pre),"PeakDate":str(peakrow["Date"]),"PeakHigh":peak})
        for n in (21,63,126):
            h=post.head(n); end=h.iloc[-1]
            horizons.append({
                "Symbol":sym,"HorizonSessions":n,"ObservedSessions":len(h),"HorizonStatus":"COMPLETE" if len(h)>=n else "PARTIAL_CACHE_WINDOW",
                "StartSession":str(first["Date"]),"StartClose":first_close,"EndSession":str(end["Date"]),"EndClose":float(end["Close"]),
                "CloseReturnPct":(float(end["Close"])/first_close-1)*100,
                "MaxHighPctFromStart":(float(h["High"].max())/first_close-1)*100,
                "MinLowPctFromStart":(float(h["Low"].min())/first_close-1)*100,
                "TargetTouched":bool((h["Low"]<=target).any()) if target is not None else "",
                "CorporateActionStatus":"NOT_AUDITED_PROVISIONAL","PnlSimulation":"NOT_PERFORMED",
            })
    pd.DataFrame(results).to_csv(OUT/"event_study_results.csv",index=False)
    pd.DataFrame(horizons).to_csv(OUT/"post_result_horizon_observations.csv",index=False)
    pd.DataFrame(windows).to_csv(OUT/"pre_result_window_verification.csv",index=False)
    pd.DataFrame(errors).to_csv(OUT/"cache_file_errors.csv",index=False)
    summary={
        "research_only":True,"cache_read_only":True,"cache_files_seen":len(files),
        "valid_price_rows":len(prices),"price_sessions":int(prices["Date"].nunique()) if not prices.empty else 0,
        "events_total":len(events),"events_with_result":sum(r.get("Status")=="PROVISIONAL_EVENT_STUDY" for r in results),
        "events_wait_for_data":sum(r.get("Status")=="WAIT_FOR_DATA" for r in results),
        "eps_decline_events":sum(r.get("EPSStatus")=="EPS_DECLINE" for r in results),
        "eps_no_decline_controls":sum(r.get("EPSStatus")=="NO_EPS_DECLINE" for r in results),
        "target_touches":sum(r.get("TargetTouchedByDailyLow") is True for r in results),
        "corporate_action_review":"NOT_AUDITED; outputs provisional",
        "method":"20 completed pre-result sessions, maximum High, annual diluted EPS ratio, post-result daily Low/Close observations",
        "no_lookahead":"announcement date excluded from pre-result window and post-result outcomes start strictly after announcement date",
        "not_trade_pnl_backtest":"No entry, exit, position sizing, fees, slippage, stop loss or P&L simulated",
        "volume_gainer_filter_used":False,"production_changes":False,
    }
    (OUT/"backtest_summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print(json.dumps(summary,indent=2))
    if summary["events_wait_for_data"]>0 or summary["events_with_result"]==0: raise SystemExit(2)

if __name__=="__main__": main()
