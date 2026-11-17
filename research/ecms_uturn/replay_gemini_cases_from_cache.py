"""Independent replay of Gemini reference setups against restored NSE V8 cache.

EOD signal on session T; entry at T+1 open only if that open remains in the
supplied valuation zone. Uses delivery % and RVOL (volume / prior 20-session
average). Long-only, non-overlapping trades, 63-session max hold, conservative
stop-first resolution when both stop and target are touched intraday.
Research only; corporate actions and costs are not adjusted.
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
 stem=path.stem; out=set()
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
def num(series):
 return pd.to_numeric(series.astype(str).str.replace("%","",regex=False).str.replace(",","",regex=False).str.strip(),errors="coerce")
def index_files(root):
 idx={}
 for p in root.rglob("*") if root.exists() else []:
  if p.is_file() and p.suffix.lower() in {".csv",".zip"}:
   for d in date_tokens(p): idx.setdefault(d,[]).append(p)
 return idx
bhav_idx=index_files(BHAV); del_idx=index_files(DELIVERY)
rows=[]; file_errors=[]
for day,paths in sorted(bhav_idx.items()):
 if len(paths)!=1:
  file_errors.append({"Date":day,"Kind":"BHAVCOPY","Reason":f"FILE_COUNT_{len(paths)}"}); continue
 try:
  df=read_table(paths[0]); needed={"TradDt","Sgmt","FinInstrmTp","TckrSymb","SctySrs","OpnPric","HghPric","LwPric","ClsPric","TtlTradgVol"}
  if not needed.issubset(df.columns): continue
  d=pd.to_datetime(df["TradDt"],errors="coerce").dt.date.astype("string")
  if set(d.dropna().tolist())!={day}: raise ValueError("TRADDT_FILENAME_MISMATCH")
  df=df[(df["Sgmt"].astype(str).str.upper()=="CM")&(df["FinInstrmTp"].astype(str).str.upper()=="STK")&(df["SctySrs"].astype(str).str.upper()=="EQ")&df["TckrSymb"].astype(str).str.upper().isin(["HDFCBANK","63MOONS"])].copy()
  for _,r in df.iterrows():
   rows.append({"Symbol":str(r["TckrSymb"]).upper(),"Date":day,"Open":float(r["OpnPric"]),"High":float(r["HghPric"]),"Low":float(r["LwPric"]),"Close":float(r["ClsPric"]),"Volume":float(r["TtlTradgVol"]),"BhavPath":str(paths[0])})
 except Exception as e: file_errors.append({"Date":day,"Kind":"BHAVCOPY","Reason":f"{type(e).__name__}:{e}"})
prices=pd.DataFrame(rows)
if prices.empty: raise RuntimeError("No HDFCBANK/63MOONS OHLCV rows found in restored cache")
if prices.duplicated(["Symbol","Date"]).any(): raise RuntimeError("Duplicate symbol/session OHLCV rows; refusing ambiguous replay")
prices=prices.sort_values(["Symbol","Date"]).reset_index(drop=True)
prices["Prior20AvgVolume"]=prices.groupby("Symbol")["Volume"].transform(lambda x:x.shift(1).rolling(20,min_periods=20).mean())
prices["RVOL"]=prices["Volume"]/prices["Prior20AvgVolume"]
delivery_rows=[]
for day,paths in sorted(del_idx.items()):
 if len(paths)!=1:
  file_errors.append({"Date":day,"Kind":"DELIVERY","Reason":f"FILE_COUNT_{len(paths)}"}); continue
 try:
  df=read_table(paths[0]); norm={str(c).strip().upper():c for c in df.columns}
  scol=norm.get("SYMBOL"); dcol=norm.get("DATE1") or norm.get("DATE"); pcol=norm.get("DELIV_PER")
  if not all([scol,dcol,pcol]): continue
  dates=pd.to_datetime(df[dcol],errors="coerce",dayfirst=True).dt.date.astype("string")
  for sym in ("HDFCBANK","63MOONS"):
   ss=df[df[scol].astype(str).str.strip().str.upper().eq(sym)&dates.eq(day)]
   if len(ss)==1: delivery_rows.append({"Symbol":sym,"Date":day,"DeliveryPct":num(ss[pcol]).iloc[0],"DeliveryPath":str(paths[0])})
   elif len(ss)>1: raise ValueError(f"DUPLICATE_DELIVERY_ROW:{sym}:{day}:{len(ss)}")
 except Exception as e: file_errors.append({"Date":day,"Kind":"DELIVERY","Reason":f"{type(e).__name__}:{e}"})
delivery=pd.DataFrame(delivery_rows)
data=prices.merge(delivery,on=["Symbol","Date"],how="left",validate="one_to_one")
trades=[]; signals=[]; summaries=[]
for case in CASES:
 s=data[data.Symbol.eq(case["Symbol"])].sort_values("Date").reset_index(drop=True).copy()
 if s.empty:
  summaries.append({"Symbol":case["Symbol"],"Status":"WAIT_FOR_DATA","Reason":"NO_CACHED_OHLCV","Sessions":0}); continue
 s["Signal"]=(s.Close.between(case["ZoneLow"],case["ZoneHigh"]))&(s.DeliveryPct>=case["DeliveryMin"])&(s.RVOL>=case["RvolMin"])
 eligible=s[s.Signal].copy()
 for _,sig in eligible.iterrows():
  signals.append({"Symbol":case["Symbol"],"SignalDate":sig.Date,"SignalClose":sig.Close,"DeliveryPct":sig.DeliveryPct,"RVOL":sig.RVOL,"ZoneLow":case["ZoneLow"],"ZoneHigh":case["ZoneHigh"]})
 i=int(s.index[s.Date.eq(sig.Date)][0]); entry_i=i+1
 if entry_i>=len(s): continue
 # Signals are replayed chronologically below; overlapping signals are skipped.
 nextrow=s.iloc[entry_i]
 entry=float(nextrow.Open)
 if not (case["ZoneLow"]<=entry<=case["ZoneHigh"]): continue
 target=entry*(1+case["TargetPct"]/100); stop=entry*(1-case["StopPct"]/100)
 end_i=min(entry_i+case["MaxHoldSessions"]-1,len(s)-1)
 exit_row=None; exit_price=None; status=None; exit_i=None
 for j in range(entry_i,end_i+1):
  bar=s.iloc[j]; op=float(bar.Open); hi=float(bar.High); lo=float(bar.Low)
  if op<=stop: exit_row=bar; exit_price=op; status="STOP_GAP"; exit_i=j; break
  if op>=target: exit_row=bar; exit_price=target; status="TARGET_GAP_CONSERVATIVE"; exit_i=j; break
  stop_hit=lo<=stop; target_hit=hi>=target
  if stop_hit: exit_row=bar; exit_price=stop; status="STOP_HIT" if not target_hit else "STOP_FIRST_BOTH_TOUCHED"; exit_i=j; break
  if target_hit: exit_row=bar; exit_price=target; status="TARGET_HIT"; exit_i=j; break
 if exit_row is None:
  exit_row=s.iloc[end_i]; exit_price=float(exit_row.Close); status="TIME_EXIT"; exit_i=end_i
 ret=(exit_price/entry-1)*100
 trades.append({"Symbol":case["Symbol"],"SignalDate":sig.Date,"EntryDate":nextrow.Date,"EntryOpen":entry,"SignalClose":float(sig.Close),"SignalDeliveryPct":float(sig.DeliveryPct),"SignalRVOL":float(sig.RVOL),"TargetPrice":target,"StopPrice":stop,"ExitDate":exit_row.Date,"ExitPrice":exit_price,"ReturnPct":ret,"Status":status,"HoldingSessions":exit_i-entry_i+1,"CorporateActionStatus":"NOT_AUDITED_RAW_PRICE_PROVISIONAL","Costs":"EXCLUDED"})
 # Skip any subsequent signal while the position is active.
 eligible=eligible[eligible.Date>s.iloc[exit_i].Date]
 # The loop iterator is already materialized; the non-overlap check is applied in the next pass below.
 # Rebuild using the trade dates after all candidates.
 # (The raw signal ledger retains every eligible signal for transparency.)
 # Avoid using a same-day signal as an independent position.
 # No portfolio compounding or sizing is simulated.
 summaries.append({"Symbol":case["Symbol"],"Status":"CACHE_REPLAY_COMPLETED","Sessions":len(s),"FirstSession":s.Date.iloc[0],"LastSession":s.Date.iloc[-1],"ZoneCloseSessions":int(s.Close.between(case["ZoneLow"],case["ZoneHigh"]).sum()),"DeliveryRows":int(s.DeliveryPct.notna().sum()),"DeliveryAndRVOLSignals":int(s.Signal.sum()),"EntryOpensInsideZone":sum(1 for x in trades if x["Symbol"]==case["Symbol"]),"EPSInputs":"NOT_SUPPLIED_BY_GEMINI_CASE; EPS valuation formula not tested"})
# Enforce non-overlap in final trade ledger (greedy earliest signal).
clean=[]
for case in CASES:
 group=sorted([t for t in trades if t["Symbol"]==case["Symbol"]],key=lambda x:x["SignalDate"])
 last_exit=""
 for t in group:
  if last_exit and t["SignalDate"]<=last_exit: continue
  clean.append(t); last_exit=t["ExitDate"]
pd.DataFrame(signals).to_csv(OUT/"gemini_case_signal_sessions.csv",index=False)
pd.DataFrame(clean).to_csv(OUT/"gemini_case_trade_replay.csv",index=False)
pd.DataFrame(file_errors).to_csv(OUT/"gemini_case_cache_errors.csv",index=False)
# Replace preliminary trade counts with non-overlapping executed counts.
for sm in summaries:
 g=[x for x in clean if x["Symbol"]==sm["Symbol"]]
 if "DeliveryAndRVOLSignals" in sm:
  sm["ExecutedTrades"]=len(g); sm["Wins"]=sum(x["ReturnPct"]>0 for x in g); sm["Losses"]=sum(x["ReturnPct"]<=0 for x in g)
  sm["WinRatePct"]=round(sm["Wins"]/len(g)*100,2) if g else None
summary={"research_only":True,"cache_read_only":True,"cache_bhavcopy_files_indexed":len(bhav_idx),"cache_delivery_files_indexed":len(del_idx),"valid_symbol_price_rows":len(prices),"delivery_rows_loaded":len(delivery),"case_summaries":summaries,"trade_execution":"signal at EOD T; next-session open entry only if open remains inside zone; target/stop evaluated on daily OHLC; stop-first if both touched; max 63 sessions","rvol_definition":"signal-session volume divided by mean volume of prior 20 completed sessions (current session excluded)","corporate_actions":"NOT_AUDITED; all price outcomes provisional","transaction_costs":"EXCLUDED","eps_formula":"NOT_TESTED; Gemini cases supplied no actual result date or annual diluted EPS periods","volume_gainer_filter_used":False,"production_changes":False}
(OUT/"gemini_case_replay_summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
print(json.dumps(summary,indent=2))
