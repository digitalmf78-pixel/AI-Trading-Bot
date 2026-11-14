"""Research-only Delivery A/B + momentum comparison; cached data only."""
from pathlib import Path
import math, re
import numpy as np
import pandas as pd

DELIVERY_DIR=Path("data/cache/delivery")
SIGNALS=Path("outputs/technical_momentum_backtest/signals.csv")
OUT=Path("outputs/delivery_momentum_research")
H=(5,10,20)

def load_reports(directory):
    reports, issues={},[]
    pat=re.compile(r"sec_bhavdata_full_(\d{2})(\d{2})(\d{4})\.csv$",re.I)
    for p in sorted(directory.glob("sec_bhavdata_full_????????.csv")):
        m=pat.fullmatch(p.name)
        if not m: continue
        day=pd.Timestamp(f"{m.group(3)}-{m.group(2)}-{m.group(1)}").normalize()
        try:
            d=pd.read_csv(p); d.columns=[str(c).strip().upper().replace(" ","_") for c in d.columns]
            req={"SYMBOL","SERIES","DATE1","DELIV_PER"}
            if not req.issubset(d.columns): raise ValueError("required columns missing")
            dates=pd.to_datetime(d.DATE1.astype(str).str.strip(),errors="coerce",dayfirst=True)
            if dates.isna().any() or set(dates.dt.normalize())!={day}: raise ValueError("DATE1 mismatch")
            d["SYMBOL"]=d.SYMBOL.astype(str).str.strip().str.upper()
            d["SERIES"]=d.SERIES.astype(str).str.strip().str.upper()
            d["DELIV_PER"]=pd.to_numeric(d.DELIV_PER,errors="coerce")
            d=d[d.SERIES.eq("EQ") & d.DELIV_PER.between(0,100)]
            d=d.loc[~d.duplicated(["SYMBOL","SERIES"],keep=False)]
            reports[day]=dict(zip(d.SYMBOL,d.DELIV_PER.astype(float)))
        except Exception as e: issues.append(f"{p.name}: {e}")
    return reports,issues

def classify(symbol,asof,reports):
    start=asof-pd.Timedelta(days=29)
    vals=[reports[d][symbol] for d in sorted(reports) if start<=d<=asof and symbol in reports[d]]
    if len(vals)<5: return ("WAIT_FOR_DATA",len(vals),0,sum(v>=60 for v in vals))
    a=sum(np.mean(vals[i-4:i+1])>=60 for i in range(4,len(vals)))
    b=sum(v>=60 for v in vals)
    status="A_AND_B" if a>=5 and b>=5 else "A_ONLY" if a>=5 else "B_ONLY" if b>=5 else "FAIL"
    return status,len(vals),a,b

def pf(x):
    gains=float(x[x>0].sum()); losses=float(-x[x<0].sum())
    return gains/losses if losses else (math.inf if gains else np.nan)

def metric(g,h):
    r=pd.to_numeric(g[f"Return{h}D_Pct"],errors="coerce").dropna()
    m=pd.to_numeric(g[f"MFE{h}D_Pct"],errors="coerce").dropna()
    p=pf(r) if len(r) else np.nan
    return {f"N{h}":len(r),f"Win{h}%":round(r.gt(0).mean()*100,2) if len(r) else np.nan,
            f"Avg{h}%":round(r.mean(),3) if len(r) else np.nan,
            f"Median{h}%":round(r.median(),3) if len(r) else np.nan,
            f"PF{h}":round(p,3) if math.isfinite(p) else p,
            f"MFE15_{h}%":round(m.ge(15).mean()*100,2) if len(m) else np.nan}

def run():
    OUT.mkdir(parents=True,exist_ok=True)
    s=pd.read_csv(SIGNALS); reports,issues=load_reports(DELIVERY_DIR)
    if not reports:
        pd.DataFrame([{"Status":"WAIT_FOR_DATA","Reason":"No valid cached Delivery reports"}]).to_csv(OUT/"comparison.csv",index=False); return
    s["Date"]=pd.to_datetime(s.Date).dt.normalize(); s["Symbol"]=s.Symbol.astype(str).str.upper().str.strip()
    cache={}
    for day,g in s.groupby("Date"):
        for sym in g.Symbol.unique(): cache[(day,sym)]=classify(sym,day,reports)
    z=[cache[(r.Date,r.Symbol)] for r in s.itertuples()]
    s["DeliveryABStatus"]=[x[0] for x in z]; s["DeliveryValidReports30D"]=[x[1] for x in z]
    s["DeliveryARollingPassCount30D"]=[x[2] for x in z]; s["DeliveryBDailyPassCount30D"]=[x[3] for x in z]
    ab=s.DeliveryABStatus.isin(["A_ONLY","B_ONLY","A_AND_B"])
    rv=s.RVOL20.ge(1.5)&s.RVOL20.lt(5)
    liq=s.AvgTradedValue20D_INR.ge(20_000_000)&s.AvgTradedValue20D_INR.lt(50_000_000)
    groups={
      "AB_QUALIFIED":ab,
      "AB_RVOL_1_5_5":ab&rv,
      "AB_RVOL_LIQ_2_5CR":ab&rv&liq,
      "AB_RVOL_LIQ_EMA_STACK":ab&rv&liq&s.EMA_STACK_20_44_50,
      "AB_RVOL_LIQ_VCP":ab&rv&liq&s.VCP_TWO_CONTRACTIONS,
      "AB_RVOL_LIQ_VCP_DRYUP":ab&rv&liq&s.VCP_TWO_CONTRACTIONS_DRYUP,
      "AB_RVOL_LIQ_BREAKOUT20":ab&rv&liq&s.BREAKOUT_20D,
      "AB_RVOL_LIQ_VCP_DRYUP_BREAKOUT20":ab&rv&liq&s.VCP_DRYUP_AND_BREAKOUT20}
    dates=sorted(s.Date.dropna().unique()); pos={d:i for i,d in enumerate(dates)}
    out=[]
    for name,mask in groups.items():
        sub=s.loc[mask].sort_values(["Symbol","Date"]); keep=[]; last={}
        for _,r in sub.iterrows():
            i=pos[r.Date]
            if r.Symbol not in last or i-last[r.Symbol]>=21: keep.append(r); last[r.Symbol]=i
        sample=pd.DataFrame(keep)
        rec={"Setup":name,"SignalRows":len(sub),"NonOverlap21":len(sample),
             "Symbols":int(sub.Symbol.nunique()),"ValidDeliveryReports":len(reports),
             "CostsSlippage":"NOT_INCLUDED","Status":"RESEARCH_ONLY_NOT_PRODUCTION_VALIDATED"}
        for h in H: rec.update(metric(sample,h))
        out.append(rec)
    pd.DataFrame(out).to_csv(OUT/"comparison.csv",index=False)
    s.to_csv(OUT/"signals_with_delivery.csv",index=False)
    pd.DataFrame({"Issue":issues}).to_csv(OUT/"delivery_file_issues.csv",index=False)
    pd.DataFrame([{"SignalRows":len(s),"DeliveryReports":len(reports),
      "DeliveryStart":min(reports).date(),"DeliveryEnd":max(reports).date(),
      "DeliveryFileIssues":len(issues),"NetworkCallsMade":False,
      "ABRule":"30 calendar days; A >=5 rolling 5-observation means >=60%; B >=5 daily observations >=60%; A OR B",
      "Liquidity":"Prior 20-session average traded value >=2Cr and <5Cr in selected combinations",
      "RVOL":"1.5 <= signal-day RVOL20 <5","CostsSlippage":"NOT_INCLUDED"}]).to_csv(OUT/"coverage.csv",index=False)
    print(pd.DataFrame(out).to_string(index=False))
    print("[DELIVERY + MOMENTUM] Research only; production scanner untouched.")

if __name__=="__main__": run()
