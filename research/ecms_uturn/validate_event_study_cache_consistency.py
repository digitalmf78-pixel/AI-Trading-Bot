"""Fail-closed consistency gate: event-study and strict NSE parser must agree."""
from __future__ import annotations
import csv, json
from pathlib import Path

root=Path("v8_cache_audit")
summary=json.loads((root/"symbol_audit_summary.json").read_text(encoding="utf-8"))
strict={r["Symbol"]:r for r in summary.get("symbols",[])}
event_rows=list(csv.DictReader(Path("uturn_cache_backtest/pre_result_window_verification.csv").open(encoding="utf-8-sig",newline="")))
errors=[]
for row in event_rows:
    sym=row["Symbol"]
    check=strict.get(sym)
    if not check:
        errors.append(f"{sym}: missing strict parser result")
        continue
    if check.get("Status")!="READY" or int(check.get("VerifiedSessions",0))!=20:
        errors.append(f"{sym}: strict parser {check.get('Status')} {check.get('VerifiedSessions')}/20 {check.get('Reason')}")
    if int(row.get("CacheMatchedSessions",0))!=20:
        errors.append(f"{sym}: event engine matched {row.get('CacheMatchedSessions')}/20")
    if check.get("Status")=="READY":
        if abs(float(row["PeakHigh"])-float(check.get("PeakHigh",row["PeakHigh"])))>0.000001:
            errors.append(f"{sym}: peak high differs between parsers")
        if str(row["PeakDate"])!=str(check.get("PeakDate","")):
            errors.append(f"{sym}: peak date differs between parsers")
if len(event_rows)!=3:
    errors.append(f"expected 3 pilot rows, found {len(event_rows)}")
out={"status":"PASS" if not errors else "BLOCKED","errors":errors,
     "strict_cache_parser":"audit_v8_cache_samples.py","event_study_parser":"run_uturn_cache_backtest.py",
     "requirement":"same restored cache snapshot; exactly 20 verified pre-result sessions per symbol; identical peak date and high"}
Path("v8_cache_audit/event_study_consistency_gate.json").write_text(json.dumps(out,indent=2),encoding="utf-8")
print(json.dumps(out,indent=2))
if errors: raise SystemExit(2)
