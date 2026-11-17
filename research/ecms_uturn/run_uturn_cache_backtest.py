"""Isolated U-Turn event study using read-only NSE V8 cache.

No orders, entries, exits, P&L, or production integration. All outputs remain
provisional until EPS source, calendar, and corporate-action audits complete.
"""
from __future__ import annotations
import csv, json, re, zipfile
from pathlib import Path
import pandas as pd

ROOT=Path(".")
CACHE=ROOT/"data/bhavcopy"
DELIVERY=ROOT/"data/cache/delivery"
OUT=ROOT/"uturn_cache_backtest"
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

def date_tokens(path):
    found=set()
    for token in re.findall(r"(?<!\d)(20\d{6})(?!\d)",path.stem):
        try: found.add(pd.to_datetime(token,format="%Y%m%d").date().isoformat())
        except Exception: pass
    for a,b,c in re.findall(r"(?<!\d)(\d{2})(\d{2})(20\d{2})(?!\d)",path.stem):
        try: found.add(pd.to_datetime(a+b+c,format="%d%m%Y").date().isoformat())
        except Exception: pass
    return found

def number(series):
    return pd.to_numeric(series.astype(str).str.replace("%","",regex=False).str.replace(",","",regex=False).str.strip(),errors="coerce")

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
            df=df[df["TradDt"].notna()
                & df["Sgmt"].astype(str).str.upper().eq("CM")
                & df["FinInstrmTp"].astype(str).str.upper().eq("STK")
                & df["SctySrs"].astype(str).str.upper().eq("EQ")
                & df["TckrSymb"].astype(str).str.upper().isin(symbols)].copy()
            if df.empty: continue
            df["Date"]=day
            for dest,src in [("Open","OpnPric"),("High","HghPric"),("Low","LwPric"),("Close","ClsPric"),("Volume","TtlTradgVol")]:
                df[dest]=pd.to_numeric(df[src],errors="coerce")
            df["TckrSymb"]=df["TckrSymb"].astype(str).str.upper().str.strip()
            df["ISIN"]=df["ISIN"].astype(str).str.strip().str.upper()
            df["CachePath"]=str(path)
            frames.append(df[["TckrSymb","Date","Open","High","Low","Close","Volume","ISIN","CachePath"]])
        except Exception as exc: errors.append({"Path":str(path),"Reason":f"{type(exc).__name__}:{exc}"})
    return (pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()),files,errors

def load_delivery(symbols):
    rows=[]; errors=[]; files=sorted(p for p in DELIVERY.rglob("*") if p.is_file() and p.suffix.lower() in {".csv",".zip"}) if DELIVERY.exists() else []
    for path in files:
        days=date_tokens(path)
        if len(days)!=1:
            errors.append({"Path":str(path),"Reason":f"DELIVERY_FILENAME_DATE_COUNT:{sorted(days)}"}); continue
        day=next(iter(days))
        try:
            df=read_frame(path); cols={str(c).strip().upper():c for c in df.columns}
            sym_col=cols.get("SYMBOL"); date_col=cols.get("DATE1") or cols.get("DATE"); pct_col=cols.get("DELIV_PER")
            if not all((sym_col,date_col,pct_col)): continue
            dates=pd.to_datetime(df[date_col],errors="coerce",dayfirst=True).dt.date.astype("string")
            selected=df[df[sym_col].astype(str).str.strip().str.upper().isin(symbols)&dates.eq(day)]
            for _,r in selected.iterrows():
                pct=number(pd.Series([r[pct_col]])).iloc[0]
                rows.append({"TckrSymb":str(r[sym_col]).strip().upper(),"Date":day,"DeliveryPct":pct,"DeliveryPath":str(path)})
        except Exception as exc: errors.append({"Path":str(path),"Reason":f"{type(exc).__name__}:{exc}"})
    frame=pd.DataFrame(rows)
    if not frame.empty and frame.duplicated(["TckrSymb","Date"]).any():
        dup=frame[frame.duplicated(["TckrSymb","Date"],keep=False)][["TckrSymb","Date"]].to_dict("records")
        raise RuntimeError(f"DUPLICATE_DELIVERY_ROWS:{dup[:10]}")
    if not frame.empty:
        invalid=frame["DeliveryPct"].notna() & ~frame["DeliveryPct"].between(0,100)
        if invalid.any(): raise RuntimeError("DELIVERY_PERCENT_OUT_OF_RANGE")
    return frame,files,errors

def main():
    events=list(csv.DictReader(EVENTS.open(encoding="utf-8-sig",newline="")))
    manifest=list(csv.DictReader(MANIFEST.open(encoding="utf-8-sig",newline="")))
    symbols={r["Symbol"].upper() for r in events}
    prices,price_files,price_errors=load_prices(symbols)
    delivery,delivery_files,delivery_errors=load_delivery(symbols)
    if prices.empty: raise RuntimeError("NO_CACHED_EVENT_SYMBOL_PRICE_ROWS")
    if prices.duplicated(["TckrSymb","Date"]).any(): raise RuntimeError("DUPLICATE_SYMBOL_SESSION_PRICE_ROWS")
    prices=prices.sort_values(["TckrSymb","Date"]).reset_index(drop=True)
    bad=prices[["Open","High","Low","Close","Volume"]].isna().any(axis=1) | (prices[["Open","High","Low","Close"]]<=0).any(axis=1) | (prices["Volume"]<0) | (prices["High"]<prices[["Open","Low","Close"]].max(axis=1)) | (prices["Low"]>prices[["Open","High","Close"]].min(axis=1))
    if bad.any(): raise RuntimeError(f"INVALID_OHLCV_ROWS:{int(bad.sum())}")
    for sym,isin in EXPECTED_ISIN.items():
        seen=set(prices.loc[prices["TckrSymb"].eq(sym),"ISIN"].unique())
        if sym in symbols and seen!={isin}: raise RuntimeError(f"ISIN_MISMATCH:{sym}:{sorted(seen)}")
    prices["Prior20AvgVolume"]=prices.groupby("TckrSymb")["Volume"].transform(lambda x:x.shift(1).rolling(20,min_periods=20).mean())
    prices["RVOL"]=prices["Volume"]/prices["Prior20AvgVolume"]
    data=prices.merge(delivery,on=["TckrSymb","Date"],how="left",validate="one_to_one")
    results=[]; horizons=[]; daily=[]; windows=[]
    for ev in events:
        sym=ev["Symbol"].upper(); event=pd.Timestamp(ev["Result_Announcement_Date"]).date().isoformat()
        prior=float(ev["Previous_FY_Diluted_EPS_INR"]); current=float(ev["Current_FY_Diluted_EPS_INR"])
        s=data[data["TckrSymb"].eq(sym)].sort_values("Date").reset_index(drop=True)
        if s.empty:
            results.append({"Symbol":sym,"Status":"WAIT_FOR_DATA","Reason":"NO_CACHED_SYMBOL_ROWS"}); continue
        expected=[r["Expected_NSE_Session"] for r in manifest if r["Symbol"].upper()==sym]
        pre=s[s["Date"].isin(expected)].copy()
        missing=sorted(set(expected)-set(pre["Date"].tolist()))
        if len(expected)!=20 or len(pre)!=20 or missing or any(d>=event for d in pre["Date"].tolist()):
            results.append({"Symbol":sym,"Status":"WAIT_FOR_DATA","Reason":f"PRE_WINDOW_INCOMPLETE_OR_LEAKAGE expected={len(expected)} present={len(pre)} missing={missing}"}); continue
        peakrow=pre.loc[pre["High"].idxmax()]; peak=float(peakrow["High"])
        eps_status="EPS_DECLINE" if current<prior else "NO_EPS_DECLINE"
        target=peak*current/prior if eps_status=="EPS_DECLINE" and prior>0 and current>0 else None
        zlow=target*0.98 if target else None; zhigh=target*1.02 if target else None
        post=s[s["Date"]>event].copy().reset_index(drop=True)
        if post.empty:
            results.append({"Symbol":sym,"Status":"WAIT_FOR_DATA","Reason":"NO_POST_RESULT_SESSIONS"}); continue
        touch_dates=[]; confirm_dates=[]; missing_delivery_touches=0
        for _,bar in post.iterrows():
            touched=bool(target is not None and float(bar["Low"])<=zhigh and float(bar["High"])>=zlow)
            delivery_pct=float(bar["DeliveryPct"]) if pd.notna(bar.get("DeliveryPct")) else None
            rvol=float(bar["RVOL"]) if pd.notna(bar.get("RVOL")) else None
            if touched: touch_dates.append(str(bar["Date"]))
            if touched and delivery_pct is None: missing_delivery_touches+=1
            confirmed=bool(touched and delivery_pct is not None and rvol is not None and delivery_pct>=60.0 and rvol>=1.5)
            if confirmed: confirm_dates.append(str(bar["Date"]))
            daily.append({
                "Symbol":sym,"Date":str(bar["Date"]),"Open":bar["Open"],"High":bar["High"],"Low":bar["Low"],"Close":bar["Close"],
                "Volume":bar["Volume"],"DeliveryPct":delivery_pct,"Prior20AvgVolume":bar["Prior20AvgVolume"],"RVOL":rvol,
                "Target":target,"ZoneLow":zlow,"ZoneHigh":zhigh,"ZoneTouched":touched,
                "SameSessionDelivery60":bool(delivery_pct is not None and delivery_pct>=60),
                "SameSessionRVOL15":bool(rvol is not None and rvol>=1.5),
                "TechnicalConfirmation":"TECHNICAL_CONFIRMATION_ONLY" if confirmed else ("WAIT_FOR_DATA" if touched and (delivery_pct is None or rvol is None) else ("ZONE_TOUCH_NOT_CONFIRMED" if touched else "NO_ZONE_TOUCH")),
            })
        first=post.iloc[0]; last=post.iloc[-1]
        results.append({
            "Symbol":sym,"Status":"PROVISIONAL_EVENT_STUDY","EPSStatus":eps_status,
            "PreviousDilutedEPS":prior,"CurrentDilutedEPS":current,"ReportingBasis":ev["Reporting_Basis"],
            "PreResultSessionsInCache":len(pre),"PreResultCalendarCrossCheck":"PENDING",
            "PeakHigh":peak,"PeakHighDate":str(peakrow["Date"]),
            "FirstPostResultSession":str(first["Date"]),"FirstPostResultClose":float(first["Close"]),
            "LatestPostResultSession":str(last["Date"]),"LatestPostResultClose":float(last["Close"]),
            "UturnTargetProvisional":target,"ZoneLow":zlow,"ZoneHigh":zhigh,
            "ZoneTouchCount":len(touch_dates),"FirstZoneTouchDate":touch_dates[0] if touch_dates else "",
            "TechnicalConfirmationCount":len(confirm_dates),"FirstTechnicalConfirmationDate":confirm_dates[0] if confirm_dates else "",
            "ZoneTouchesMissingDelivery":missing_delivery_touches,
            "LatestCloseVsTargetPct":(float(last["Close"])/target-1)*100 if target else "",
            "CorporateActionStatus":"NOT_AUDITED_PROVISIONAL","EPSSourceAudit":"VERIFIED_OFFICIAL_CONSOLIDATED_ANNUAL_DILUTED_EPS_VALUES",
            "Interpretation":"EVENT_STUDY_ONLY_NO_ENTRY_EXIT_OR_PNL",
            "EPSAnnualReportURL":ev["Official_Annual_Report_URL"],"ResultFilingURL":ev["Official_Result_Filing_URL"],
        })
        windows.append({"Symbol":sym,"ExpectedSessions":20,"CacheMatchedSessions":len(pre),"PeakDate":str(peakrow["Date"]),"PeakHigh":peak,"CalendarCrossCheck":"PENDING"})
        for n in (21,63,126):
            h=post.head(n); end=h.iloc[-1]
            horizons.append({
                "Symbol":sym,"HorizonSessions":n,"ObservedSessions":len(h),"HorizonStatus":"COMPLETE" if len(h)>=n else "PARTIAL_CACHE_WINDOW",
                "StartSession":str(first["Date"]),"StartClose":float(first["Close"]),"EndSession":str(end["Date"]),"EndClose":float(end["Close"]),
                "CloseReturnPct":(float(end["Close"])/float(first["Close"])-1)*100,
                "MaxHighPctFromStart":(float(h["High"].max())/float(first["Close"])-1)*100,
                "MinLowPctFromStart":(float(h["Low"].min())/float(first["Close"])-1)*100,
                "TargetZoneTouched":bool((h["Low"].le(zhigh)&h["High"].ge(zlow)).any()) if target else "",
                "TechnicalConfirmationCount":sum(1 for d in daily if d["Symbol"]==sym and d["Date"] in set(h["Date"].astype(str)) and d["TechnicalConfirmation"]=="TECHNICAL_CONFIRMATION_ONLY") if target else 0,
                "CorporateActionStatus":"NOT_AUDITED_PROVISIONAL","PnlSimulation":"NOT_PERFORMED",
            })
    pd.DataFrame(results).to_csv(OUT/"event_study_results.csv",index=False)
    pd.DataFrame(horizons).to_csv(OUT/"post_result_horizon_observations.csv",index=False)
    pd.DataFrame(windows).to_csv(OUT/"pre_result_window_verification.csv",index=False)
    pd.DataFrame(daily).to_csv(OUT/"post_result_daily_observations.csv",index=False)
    pd.DataFrame(price_errors+delivery_errors).to_csv(OUT/"cache_file_errors.csv",index=False)
    summary={
        "research_only":True,"cache_read_only":True,"price_files_seen":len(price_files),"delivery_files_seen":len(delivery_files),
        "valid_price_rows":len(prices),"price_sessions":int(prices["Date"].nunique()),"delivery_rows_matched":int(data["DeliveryPct"].notna().sum()),
        "events_total":len(events),"events_with_result":sum(r.get("Status")=="PROVISIONAL_EVENT_STUDY" for r in results),
        "events_wait_for_data":sum(r.get("Status")=="WAIT_FOR_DATA" for r in results),
        "eps_decline_events":sum(r.get("EPSStatus")=="EPS_DECLINE" for r in results),
        "eps_no_decline_controls":sum(r.get("EPSStatus")=="NO_EPS_DECLINE" for r in results),
        "zone_touches":sum(int(r.get("ZoneTouchCount",0)) for r in results),
        "technical_confirmations":sum(int(r.get("TechnicalConfirmationCount",0)) for r in results),
        "corporate_action_review":"PENDING; all outcomes provisional",
        "calendar_cross_check":"PENDING; cache date matches are not independent exchange-calendar verification",
        "eps_source_audit":"Official filing URLs recorded; EPS table and basis content review still required",
        "method":"20 pre-result cache sessions; peak High; annual diluted EPS ratio; zone overlap; same-session delivery >=60% and RVOL >=1.5; 21/63/126 post-result observations",
        "no_lookahead":"announcement session excluded; post-result observations begin strictly after announcement date",
        "not_trade_pnl_backtest":"No entry, exit, position sizing, fees, slippage, stop loss or P&L simulated",
        "random_sampling":"NOT_RANDOMIZED; three-symbol pilot sample retained as supplied; do not generalize",
        "volume_gainer_filter_used":False,"production_changes":False,
    }
    (OUT/"backtest_summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print(json.dumps(summary,indent=2))
    if summary["events_wait_for_data"]>0 or summary["events_with_result"]==0: raise SystemExit(2)

if __name__=="__main__": main()
