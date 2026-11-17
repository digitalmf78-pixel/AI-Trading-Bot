"""Select only complete, provenance-backed fundamental rows and run two-sided price-context research."""
from __future__ import annotations
import csv, json, math, re
from pathlib import Path
import pandas as pd
from strategies.ecms.uturn_two_sided import assess_two_sided_price_context

ROOT=Path("."); OUT=ROOT/"v8_cache_audit"; OUT.mkdir(exist_ok=True)
METRICS=ROOT/"data/inputs/fundamental_metrics.csv"
FILINGS=ROOT/"outputs/v8_official_financial_results_filings.csv"
BHAV=ROOT/"data/bhavcopy"
REQUIRED={
 "RevenueGrowthPct","ProfitGrowthPct","ROEPercent","ROCEPercent",
 "DebtToEquity","InterestCoverage","OperatingCashFlowINR",
}
MAP_FIELDS={
 "source":"MetricSourcesJSON","url":"MetricSourceURLsJSON",
 "period":"MetricSourcePeriodsJSON","basis":"MetricCalculationBasesJSON",
 "currency":"MetricSourceCurrenciesJSON",
}
NULLS={"","nan","none","null","na","n/a","-"}
def clean(v):
 s="" if v is None else str(v).strip()
 return "" if s.lower() in NULLS else s
def mapping(row, col):
 try:
  v=json.loads(clean(row.get(col)))
  return v if isinstance(v,dict) else {}
 except Exception: return {}
def finite(v):
 try: return math.isfinite(float(v))
 except Exception: return False
def official_filing_match(row, filings):
 required={"TckrSymb","FinancialPeriodEnd","PublicationDate","PublicationDateStatus","OfficialFilingURL"}
 if filings.empty or not required.issubset(filings.columns): return False,"FILING_REGISTER_UNAVAILABLE"
 sym=clean(row.get("TckrSymb")).upper(); period=clean(row.get("FinancialPeriodEnd"))[:10]
 pub=clean(row.get("PublicationDate"))[:10]; url=clean(row.get("OfficialFilingURL"))
 if not url: return False,"OFFICIAL_FILING_URL_MISSING"
 f=filings[
  filings["TckrSymb"].astype(str).str.upper().eq(sym)
  & filings["FinancialPeriodEnd"].astype(str).str[:10].eq(period)
  & filings["OfficialFilingURL"].astype(str).eq(url)
 ]
 if len(f)!=1: return False,f"FILING_EXACT_MATCH_COUNT_{len(f)}"
 x=f.iloc[0]
 if clean(x.get("PublicationDate"))[:10]!=pub: return False,"FILING_PUBLICATION_DATE_MISMATCH"
 if clean(x.get("PublicationDateStatus")).upper()!="VERIFIED": return False,"FILING_PUBLICATION_DATE_NOT_VERIFIED"
 if not url.startswith("https://nsearchives.nseindia.com/corporate/xbrl/"): return False,"FILING_URL_NOT_OFFICIAL_NSE_XBRL"
 return True,"OFFICIAL_FILING_METADATA_MATCHED_VALUE_FACTS_STILL_REQUIRE_METRIC_LEVEL_VERIFICATION"

if not METRICS.is_file(): raise FileNotFoundError(METRICS)
metrics=pd.read_csv(METRICS,dtype=str,keep_default_na=False)
filings=pd.read_csv(FILINGS,dtype=str,keep_default_na=False) if FILINGS.is_file() else pd.DataFrame()
if "TckrSymb" not in metrics: raise ValueError("Fundamental cache has no TckrSymb")
metrics["TckrSymb"]=metrics["TckrSymb"].astype(str).str.strip().str.upper()
counts=metrics.groupby("TckrSymb").size()
fund_rows=[]; eligible=[]
for sym, group in metrics.groupby("TckrSymb",sort=True):
 if len(group)!=1:
  fund_rows.append({"Symbol":sym,"Status":"WAIT_FOR_DATA","Reason":f"DUPLICATE_METRIC_ROWS_{len(group)}"}); continue
 row=group.iloc[0].to_dict()
 missing=[m for m in sorted(REQUIRED) if m not in row or not finite(row.get(m))]
 if missing:
  fund_rows.append({"Symbol":sym,"Status":"WAIT_FOR_DATA","Reason":"MISSING_OR_NON_NUMERIC_METRICS:"+",".join(missing)}); continue
 absent=[]
 maps={k:mapping(row,col) for k,col in MAP_FIELDS.items()}
 for metric in REQUIRED:
  for kind, mp in maps.items():
   if kind == "basis" and not clean(mp.get(metric)) and clean(row.get("MetricCalculationBasis")).upper() not in {"","LEGACY_CACHE_BASIS_UNKNOWN","UNALIGNED_PROVIDER_SNAPSHOT"}:
    continue
   if not clean(mp.get(metric)):
    absent.append(f"{metric}:{kind}")
 if absent:
  fund_rows.append({"Symbol":sym,"Status":"WAIT_FOR_DATA","Reason":"MISSING_PER_METRIC_PROVENANCE:"+",".join(absent)}); continue
 if clean(row.get("MetricPeriodAlignmentStatus")).upper()!="VERIFIED":
  fund_rows.append({"Symbol":sym,"Status":"WAIT_FOR_DATA","Reason":"METRIC_PERIOD_ALIGNMENT_NOT_VERIFIED"}); continue
 basis=clean(row.get("MetricCalculationBasis")).upper()
 if basis in {"","LEGACY_CACHE_BASIS_UNKNOWN","UNALIGNED_PROVIDER_SNAPSHOT"}:
  fund_rows.append({"Symbol":sym,"Status":"WAIT_FOR_DATA","Reason":"ROW_CALCULATION_BASIS_NOT_ACCEPTED"}); continue
 if not clean(row.get("FinancialPeriodEnd")) or not clean(row.get("PublicationDate")):
  fund_rows.append({"Symbol":sym,"Status":"WAIT_FOR_DATA","Reason":"FINANCIAL_PERIOD_OR_PUBLICATION_DATE_MISSING"}); continue
 if clean(row.get("PublicationDateStatus")).upper()!="VERIFIED":
  fund_rows.append({"Symbol":sym,"Status":"WAIT_FOR_DATA","Reason":"PUBLICATION_DATE_NOT_VERIFIED"}); continue
 ok, filing_status=official_filing_match(row,filings)
 if not ok:
  fund_rows.append({"Symbol":sym,"Status":"WAIT_FOR_DATA","Reason":filing_status,
   "OfficialFilingURL":clean(row.get("OfficialFilingURL")),"OfficialFilingSource":clean(row.get("OfficialFilingSource")),
   "RowCalculationBasis":clean(row.get("MetricCalculationBasis"))}); continue
 # Require each metric's own source period and basis, and no mixed-period declaration.
 periods={clean(maps["period"].get(m)) for m in REQUIRED}
 def fiscal_year(period):
  years=re.findall(r"20[0-9]{2}",period)
  return years[-1] if years else ""
 period_years={fiscal_year(p) for p in periods}
 if "" in periods or "" in period_years or len(period_years)>1:
  # Growth may legitimately encode a consecutive FY pair; compare its latest
  # FY to the reporting FY of the ratio/cash-flow metrics.
  fund_rows.append({"Symbol":sym,"Status":"WAIT_FOR_DATA","Reason":"METRIC_SOURCE_PERIODS_MISSING_OR_FISCAL_YEAR_MISMATCH"}); continue
 currencies={clean(maps["currency"].get(m)).upper() for m in REQUIRED}
 if "" in currencies:
  fund_rows.append({"Symbol":sym,"Status":"WAIT_FOR_DATA","Reason":"METRIC_SOURCE_CURRENCY_MISSING"}); continue
 eligible.append((sym,row))
 fund_rows.append({
  "Symbol":sym,"Status":"COMPLETE_FIELDS_PROVENANCE","Reason":"All 7 numeric core metrics and per-metric source/URL/period/basis/currency present; period and filing metadata matched",
  "FinancialPeriodEnd":clean(row.get("FinancialPeriodEnd")),"PublicationDate":clean(row.get("PublicationDate")),
  "CalculationBasis":basis,"OfficialFilingMetadataStatus":filing_status,
  "OfficialFilingURL":clean(row.get("OfficialFilingURL")),"OfficialFilingSource":clean(row.get("OfficialFilingSource")),
  "MetricValueVerification":"NOT_INFERRED_FROM_CACHE_METADATA; separate XBRL fact-level verification required",
  **{m:row[m] for m in sorted(REQUIRED)}
 })
# Index cached UDiFF files by session encoded in filename; use exact row date validation.
def date_tokens(path):
 stem=path.stem; out=set()
 for token in re.findall(r"(?<!\d)(20\d{6})(?!\d)",stem):
  try: out.add(pd.to_datetime(token,format="%Y%m%d").date().isoformat())
  except Exception: pass
 for a,b,c in re.findall(r"(?<!\d)(\d{2})(\d{2})(20\d{2})(?!\d)",stem):
  try: out.add(pd.to_datetime(a+b+c,format="%d%m%Y").date().isoformat())
  except Exception: pass
 return out
file_index={}
for p in BHAV.rglob("*") if BHAV.exists() else []:
 if p.is_file() and p.suffix.lower() in {".csv",".zip"}:
  for day in date_tokens(p): file_index.setdefault(day,[]).append(p)
def read_file(path):
 if path.suffix.lower()==".zip":
  import zipfile
  with zipfile.ZipFile(path) as z:
   names=[n for n in z.namelist() if n.lower().endswith(".csv")]
   if len(names)!=1: raise ValueError(f"ZIP CSV count {len(names)}")
   with z.open(names[0]) as f: return pd.read_csv(f,dtype=str)
 return pd.read_csv(path,dtype=str,encoding="utf-8-sig")
frames=[]; file_errors=[]
for day, paths in sorted(file_index.items()):
 if len(paths)!=1:
  file_errors.append({"Date":day,"Reason":f"AMBIGUOUS_CACHE_FILE_COUNT_{len(paths)}"}); continue
 try:
  df=read_file(paths[0]); needed={"TradDt","Sgmt","FinInstrmTp","TckrSymb","SctySrs","HghPric","LwPric","ClsPric","TtlTradgVol"}
  if not needed.issubset(df.columns): raise ValueError("UDiFF schema incomplete")
  dates=pd.to_datetime(df["TradDt"],errors="coerce").dt.date.astype("string")
  if set(dates.dropna().tolist())!={day}: raise ValueError("Internal TradDt does not match filename session")
  df=df[(df["Sgmt"].astype(str).str.upper()=="CM") & (df["FinInstrmTp"].astype(str).str.upper()=="STK") & (df["SctySrs"].astype(str).str.upper()=="EQ")].copy()
  df["Date"]=day; df["CachePath"]=str(paths[0]); frames.append(df[["TckrSymb","Date","HghPric","LwPric","ClsPric","TtlTradgVol","CachePath"]])
 except Exception as e: file_errors.append({"Date":day,"Reason":f"{type(e).__name__}:{e}"})
all_bhav=pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()
tech_rows=[]
for sym,row in eligible:
 if all_bhav.empty:
  tech_rows.append({"Symbol":sym,"Status":"WAIT_FOR_DATA","Reason":"NO_VALID_CACHED_UDIFF_BHAVCOPY"}); continue
 s=all_bhav[all_bhav["TckrSymb"].astype(str).str.upper().eq(sym)].copy()
 if s.empty:
  tech_rows.append({"Symbol":sym,"Status":"WAIT_FOR_DATA","Reason":"NO_SYMBOL_OHLCV_ROWS"}); continue
 if s["Date"].duplicated().any():
  tech_rows.append({"Symbol":sym,"Status":"WAIT_FOR_DATA","Reason":"DUPLICATE_SYMBOL_SESSION_ROWS"}); continue
 s=s.sort_values("Date")
 o=pd.DataFrame({
  "Date":s["Date"],"High":pd.to_numeric(s["HghPric"],errors="coerce"),
  "Low":pd.to_numeric(s["LwPric"],errors="coerce"),"Close":pd.to_numeric(s["ClsPric"],errors="coerce"),
  "Volume":pd.to_numeric(s["TtlTradgVol"],errors="coerce"),"SourceURL":s["CachePath"],
 })
 result=assess_two_sided_price_context(o)
 tech_rows.append({
  "Symbol":sym,"Status":result.get("status"),"Reason":result.get("reason"),
  "DataSessions":len(o),"FirstSession":str(o["Date"].iloc[0]),"LastSession":str(o["Date"].iloc[-1]),
  "Close":result.get("close"),"RSI14":result.get("rsi"),"PreviousRSI14":result.get("previous_rsi"),
  "SMA20":result.get("sma_fast"),"SMA50":result.get("sma_slow"),
  "ExtensionPctVsSMA20":result.get("extension_pct_vs_sma_fast"),
  "VolumeRatioVsPrior20":result.get("volume_ratio_vs_prior_20"),
  "DownsideValuationZone":"NOT_SUPPLIED; bottom-side valuation-zone test not activated",
  "Interpretation":result.get("interpretation",""),
 })
pd.DataFrame(fund_rows).to_csv(OUT/"fundamental_completeness_all_symbols.csv",index=False)
pd.DataFrame(tech_rows).to_csv(OUT/"two_sided_complete_fundamentals_only.csv",index=False)
pd.DataFrame(file_errors).to_csv(OUT/"bhavcopy_file_validation_errors.csv",index=False)
summary={
 "research_only":True,"cache_source":"shared NSE V8 cache restored read-only",
 "metric_universe_symbols":int(metrics["TckrSymb"].nunique()),
 "complete_fundamental_symbols":len(eligible),
 "incomplete_or_unverified_symbols":len(fund_rows)-len(eligible),
 "two_sided_rows":len(tech_rows),
 "two_sided_status_counts":pd.DataFrame(tech_rows)["Status"].value_counts().to_dict() if tech_rows else {},
 "official_metric_value_verification":"NOT ASSERTED; this gate verifies populated values and provenance metadata, not each underlying XBRL fact",
 "bottom_side_valuation_zone":"NOT RUN; requires independently verified annual diluted EPS and corporate-action-adjusted peak window",
 "signals_or_orders":False,
 "bhavcopy_dates_indexed":len(file_index),"valid_bhavcopy_sessions_loaded":len(frames),"bhavcopy_file_errors":len(file_errors),
}
(OUT/"complete_fundamentals_two_sided_summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
print(json.dumps(summary,indent=2))
