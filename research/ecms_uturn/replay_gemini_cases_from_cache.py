"""Independent replay of Gemini reference setups against restored NSE V8 cache.

Signal is evaluated after EOD session T. Entry is next-session open only if
that open remains inside the supplied zone. Delivery % is from the same
signal session; RVOL = signal volume / prior 20-session mean volume.
One non-overlapping long trade per symbol at a time; max hold 63 sessions.
If stop and target are both touched intraday, stop is assumed first.
Research only; no corporate-action adjustment, costs or sizing.
"""
from __future__ import annotations
import json, re, zipfile
from pathlib import Path
import pandas as pd

ROOT=Path(".")
BHAV=ROOT/"data/bhavcopy"
DELIVERY=ROOT/"data/cache/delivery"
OUT=ROOT/"uturn_cache_backtest"
OUT.mkdir(exist_ok=True)
CASES=[
 {"Symbol":"HDFCBANK","Name":"HDFC Bank","ZoneLow":1650.0,"ZoneHigh":1690.0,"DeliveryMin":60.0,"RvolMin":1.5,"TargetPct":12.0,"StopPct":4.0,"MaxHoldSessions":63},
 {"Symbol":"63MOONS","Name":"63 Moons Technologies","ZoneLow":425.0,"ZoneHigh":450.0,"DeliveryMin":60.0,"RvolMin":1.5,"TargetPct":15.0,"StopPct":5.0,"MaxHoldSessions":63},
]

def date_tokens(path):
    stem=path.stem
    out=set()
    for token in re.findall(r"(?<!\d)(20\d{6})(?!\d)",stem):
        try: out.add(pd.to_datetime(token,format="%Y%m%d").date().isoformat())
        except Exception: pass
    for a,b,c in re.findall(r"(?<!\d)(\d{2})(\d{2})(20\d{2})(?!\d)",stem):
        try: out.add(pd.to_datetime(a+b+c,format="%d%m%Y").date().isoformat())
        except Exception: pass
    return out

def read_table(path):
    if path.suffix.lower()==".zip":
        with zipfile.ZipFile(path) as z:
            names=[n for n in z.namelist() if n.lower().endswith(".csv")]
            if len(names)!=1: raise ValueError(f"ZIP CSV count={len(names)}")
            with z.open(names[0]) as f: return pd.read_csv(f,dtype=str)
    return pd.read_csv(path,dtype=str,encoding="utf-8-sig")

def number(series):
    return pd.to_numeric(series.astype(str).str.replace("%","",regex=False).str.replace(",","",regex=False).str.strip(),errors="coerce")

def index_files(root):
    idx={}
    for path in root.rglob("*") if root.exists() else []:
        if path.is_file() and path.suffix.lower() in {".csv",".zip"}:
            for day in date_tokens(path): idx.setdefault(day,[]).append(path)
    return idx

bhav_index=index_files(BHAV)
delivery_index=index_files(DELIVERY)
price_rows=[]
delivery_rows=[]
file_errors=[]

for day, paths in sorted(bhav_index.items()):
    if len(paths)!=1:
        file_errors.append({"Date":day,"Kind":"BHAVCOPY","Reason":f"FILE_COUNT_{len(paths)}"})
        continue
    try:
        df=read_table(paths[0])
        required={"TradDt","Sgmt","FinInstrmTp","TckrSymb","SctySrs","OpnPric","HghPric","LwPric","ClsPric","TtlTradgVol"}
        if not required.issubset(df.columns): continue
        actual=pd.to_datetime(df["TradDt"],errors="coerce").dt.date.astype("string").dropna().unique().tolist()
        if actual!=[day] and set(actual)!={day}: raise ValueError("TRADDT_FILENAME_MISMATCH")
        df=df[
            df["Sgmt"].astype(str).str.upper().eq("CM")
            & df["FinInstrmTp"].astype(str).str.upper().eq("STK")
            & df["SctySrs"].astype(str).str.upper().eq("EQ")
            & df["TckrSymb"].astype(str).str.upper().isin(["HDFCBANK","63MOONS"])
        ]
        for _, row in df.iterrows():
            vals=[float(row[c]) for c in ("OpnPric","HghPric","LwPric","ClsPric","TtlTradgVol")]
            op,hi,lo,cl,vol=vals
            if min(op,hi,lo,cl)<=0 or vol<0 or hi<max(lo,cl,op) or lo>min(hi,cl,op):
                raise ValueError(f"INVALID_OHLCV:{row['TckrSymb']}:{day}")
            price_rows.append({"Symbol":str(row["TckrSymb"]).upper(),"Date":day,"Open":op,"High":hi,"Low":lo,"Close":cl,"Volume":vol,"BhavPath":str(paths[0])})
    except Exception as exc:
        file_errors.append({"Date":day,"Kind":"BHAVCOPY","Reason":f"{type(exc).__name__}:{exc}"})

for day, paths in sorted(delivery_index.items()):
    if len(paths)!=1:
        file_errors.append({"Date":day,"Kind":"DELIVERY","Reason":f"FILE_COUNT_{len(paths)}"})
        continue
    try:
        df=read_table(paths[0])
        norm={str(c).strip().upper():c for c in df.columns}
        sym_col=norm.get("SYMBOL")
        date_col=norm.get("DATE1") or norm.get("DATE")
        pct_col=norm.get("DELIV_PER")
        if not all([sym_col,date_col,pct_col]): continue
        dates=pd.to_datetime(df[date_col],errors="coerce",dayfirst=True).dt.date.astype("string")
        for symbol in ("HDFCBANK","63MOONS"):
            selected=df[df[sym_col].astype(str).str.strip().str.upper().eq(symbol)&dates.eq(day)]
            if len(selected)==1:
                delivery_rows.append({"Symbol":symbol,"Date":day,"DeliveryPct":number(selected[pct_col]).iloc[0],"DeliveryPath":str(paths[0])})
            elif len(selected)>1:
                raise ValueError(f"DUPLICATE_DELIVERY_ROW:{symbol}:{day}:{len(selected)}")
    except Exception as exc:
        file_errors.append({"Date":day,"Kind":"DELIVERY","Reason":f"{type(exc).__name__}:{exc}"})

prices=pd.DataFrame(price_rows)
if prices.empty: raise RuntimeError("No HDFCBANK/63MOONS OHLCV rows found in restored cache")
if prices.duplicated(["Symbol","Date"]).any(): raise RuntimeError("Duplicate symbol/session OHLCV rows; refusing ambiguous replay")
prices=prices.sort_values(["Symbol","Date"]).reset_index(drop=True)
prices["Prior20AvgVolume"]=prices.groupby("Symbol")["Volume"].transform(lambda x:x.shift(1).rolling(20,min_periods=20).mean())
prices["RVOL"]=prices["Volume"]/prices["Prior20AvgVolume"]
delivery=pd.DataFrame(delivery_rows)
if not delivery.empty and delivery.duplicated(["Symbol","Date"]).any():
    raise RuntimeError("Duplicate symbol/session delivery rows; refusing ambiguous replay")
data=prices.merge(delivery,on=["Symbol","Date"],how="left",validate="one_to_one")

all_signals=[]
all_trades=[]
summaries=[]
for case in CASES:
    symbol=case["Symbol"]
    s=data[data["Symbol"].eq(symbol)].sort_values("Date").reset_index(drop=True).copy()
    if s.empty:
        summaries.append({"Symbol":symbol,"Status":"WAIT_FOR_DATA","Reason":"NO_CACHED_OHLCV","Sessions":0})
        continue
    s["Signal"]=(
        s["Close"].between(case["ZoneLow"],case["ZoneHigh"])
        & (s["DeliveryPct"]>=case["DeliveryMin"])
        & (s["RVOL"]>=case["RvolMin"])
    )
    signal_indices=list(s.index[s["Signal"]])
    zone_mask=s["Close"].between(case["ZoneLow"],case["ZoneHigh"])
    delivery_mask=s["DeliveryPct"]>=case["DeliveryMin"]
    rvol_mask=s["RVOL"]>=case["RvolMin"]
    for i in signal_indices:
        sig=s.iloc[i]
        all_signals.append({"Symbol":symbol,"SignalDate":sig["Date"],"SignalClose":sig["Close"],"DeliveryPct":sig["DeliveryPct"],"RVOL":sig["RVOL"],"ZoneLow":case["ZoneLow"],"ZoneHigh":case["ZoneHigh"]})
    executed=[]
    last_exit_index=-1
    for i in signal_indices:
        if i<=last_exit_index or i+1>=len(s): continue
        signal=s.iloc[i]
        entry_bar=s.iloc[i+1]
        entry=float(entry_bar["Open"])
        if not (case["ZoneLow"]<=entry<=case["ZoneHigh"]): continue
        target=entry*(1+case["TargetPct"]/100)
        stop=entry*(1-case["StopPct"]/100)
        last_i=min(i+case["MaxHoldSessions"],len(s)-1)
        exit_bar=None
        exit_price=None
        exit_status=""
        exit_i=None
        for j in range(i+1,last_i+1):
            bar=s.iloc[j]
            op,hi,lo=float(bar["Open"]),float(bar["High"]),float(bar["Low"])
            if op<=stop:
                exit_bar,exit_price,exit_status,exit_i=bar,op,"STOP_GAP",j
                break
            if op>=target:
                exit_bar,exit_price,exit_status,exit_i=bar,target,"TARGET_GAP_CONSERVATIVE",j
                break
            stop_hit=lo<=stop
            target_hit=hi>=target
            if stop_hit:
                exit_bar,exit_price,exit_status,exit_i=bar,stop,("STOP_FIRST_BOTH_TOUCHED" if target_hit else "STOP_HIT"),j
                break
            if target_hit:
                exit_bar,exit_price,exit_status,exit_i=bar,target,"TARGET_HIT",j
                break
        if exit_bar is None:
            exit_bar=s.iloc[last_i]
            exit_price=float(exit_bar["Close"])
            exit_status="TIME_EXIT"
            exit_i=last_i
        ret=(exit_price/entry-1)*100
        trade={"Symbol":symbol,"SignalDate":signal["Date"],"EntryDate":entry_bar["Date"],"EntryOpen":entry,"SignalClose":float(signal["Close"]),"SignalDeliveryPct":float(signal["DeliveryPct"]),"SignalRVOL":float(signal["RVOL"]),"TargetPrice":target,"StopPrice":stop,"ExitDate":exit_bar["Date"],"ExitPrice":exit_price,"ReturnPct":ret,"Status":exit_status,"HoldingSessions":exit_i-i,"CorporateActionStatus":"NOT_AUDITED_RAW_PRICE_PROVISIONAL","Costs":"EXCLUDED"}
        executed.append(trade)
        last_exit_index=exit_i
    all_trades.extend(executed)
    wins=sum(t["ReturnPct"]>0 for t in executed)
    losses=sum(t["ReturnPct"]<=0 for t in executed)
    summaries.append({
        "Symbol":symbol,"Status":"CACHE_REPLAY_COMPLETED","Sessions":len(s),
        "FirstSession":s["Date"].iloc[0],"LastSession":s["Date"].iloc[-1],
        "OHLCVRows":len(s),"DeliveryRows":int(s["DeliveryPct"].notna().sum()),
        "ObservedCloseMin":float(s["Close"].min()),"ObservedCloseMax":float(s["Close"].max()),
        "ObservedLowMin":float(s["Low"].min()),"ObservedHighMax":float(s["High"].max()),
        "ObservedCloseMinDate":str(s.loc[s["Close"].idxmin(),"Date"]),"ObservedCloseMaxDate":str(s.loc[s["Close"].idxmax(),"Date"]),
        "CloseMin":round(float(s["Close"].min()),2),"CloseMax":round(float(s["Close"].max()),2),
        "DeliveryPctMin":round(float(s["DeliveryPct"].min()),2) if s["DeliveryPct"].notna().any() else None,
        "DeliveryPctMax":round(float(s["DeliveryPct"].max()),2) if s["DeliveryPct"].notna().any() else None,
        "SessionsDeliveryAtLeast60":int(delivery_mask.sum()),
        "SessionsRVOLAtLeast1_5":int(rvol_mask.sum()),
        "SessionsCloseInZoneAndDelivery60":int((zone_mask & delivery_mask).sum()),
        "SessionsCloseInZoneAndRVOL15":int((zone_mask & rvol_mask).sum()),
        "SessionsDelivery60AndRVOL15":int((delivery_mask & rvol_mask).sum()),
        "ClosesInsideZone":int(zone_mask.sum()),
        "ValidEODSignals":len(signal_indices),
        "NextOpenStillInsideZone":sum(1 for i in signal_indices if i+1<len(s) and case["ZoneLow"]<=float(s.iloc[i+1]["Open"])<=case["ZoneHigh"]),
        "ExecutedNonOverlappingTrades":len(executed),"Wins":wins,"Losses":losses,
        "WinRatePct":round(wins/len(executed)*100,2) if executed else None,
        "EPSInputs":"NOT_SUPPLIED; EPS valuation formula not tested",
    })

pd.DataFrame(all_signals).to_csv(OUT/"gemini_case_signal_sessions.csv",index=False)
pd.DataFrame(all_trades).to_csv(OUT/"gemini_case_trade_replay.csv",index=False)
pd.DataFrame(file_errors).to_csv(OUT/"gemini_case_cache_errors.csv",index=False)
summary={
 "research_only":True,"cache_read_only":True,
 "cache_bhavcopy_files_indexed":len(bhav_index),"cache_delivery_files_indexed":len(delivery_index),
 "valid_symbol_price_rows":len(prices),"delivery_rows_loaded":len(delivery),
 "case_summaries":summaries,
 "entry_rule":"EOD signal on T; enter next session open only if open remains inside supplied zone",
 "signal_rule":"Signal-session close inside zone AND delivery percentage >= 60 AND RVOL >= 1.5",
 "rvol_definition":"signal-session volume divided by prior 20 completed sessions' average volume; current session excluded",
 "exit_rule":"first target +12% / stop -4% for HDFCBANK; target +15% / stop -5% for 63MOONS; maximum 63 sessions",
 "intraday_ambiguity":"stop-first when both stop and target fall within same daily candle; gap-through-stop exits at open",
 "corporate_actions":"NOT_AUDITED; raw-price outcomes provisional",
 "transaction_costs":"EXCLUDED",
 "eps_formula":"NOT_TESTED; no actual result date or annual diluted EPS periods supplied",
 "volume_gainer_filter_used":False,"production_changes":False,
}
(OUT/"gemini_case_replay_summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
print(json.dumps(summary,indent=2))
