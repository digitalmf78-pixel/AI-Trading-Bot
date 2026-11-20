# ECMS P0–P8 live audit — 2026-11-20

**Audited run:** [Manual Morning run 44676678821](https://github.com/digitalmf78-pixel/AI-Trading-Bot/actions/runs/44676678821)  
**Artifact:** `ecms-volume-gainers-morning-44676678821`  
**Scope:** ECMS only. NSE V8 production workflow, code, providers, thresholds, caches and selection remain untouched. No historical backtesting.

## Run facts

- Manual trigger at 10:16:59 IST; router selected `MORNING` / `MANUAL_TIME_ROUTED_MORNING`.
- Route and Morning jobs completed successfully; EOD job correctly skipped.
- NSE page response: 17 eligible Main Board candidates; page CSV exported with 17 rows.
- Comparison: 23 previous-EOD symbols; 1 page-presence repeat, 16 new Morning entries, 22 EOD-only symbols.
- Prior-session RVOL available for 15/17; missing for 2.
- Fundamental assessment: 17/17 continued research; 12 had all seven metric values populated, 5 partial; no fundamental PASS/FAIL.
- Telegram: four report parts (message IDs 2400–2403) and full NSE page CSV (message ID 2404, 15,735 bytes) delivered successfully.
- Current Morning snapshot was saved; this run is the Morning leg only. Same-day EOD comparison and next-session EOD-reference consumption still need a separate EOD run to complete P0's lifecycle proof.

## Phase status

| Phase | Status | Evidence / blocker |
|---|---|---|
| P0 Workflow protection | PARTIAL — Morning verified | Route, snapshot save, cache restore/save, artifact and Telegram all succeeded. EOD comparison leg and next-session reference lifecycle still need verification. |
| P1 Fundamentals | PARTIAL — coverage exists, trust/freshness unresolved | All 17 stocks have metric coverage rows (119 metric observations). Every metric row is anchored to 2026-03-31; all 17 are labelled 3Q_OLD. Summary: 11 official XBRL verified, 13 provider mismatches, 50 derived reconciliations required, 47 filing metadata not confirmed, 6 provider-only. Seven symbols have missing filing URLs; seven symbols lack matched filing metadata. |
| P2 Volume origin | INCOMPLETE | Existing page/20-session RVOL fields only; Morning prior-session RVOL available for 15/17. The artifact does not provide a session-aligned 5/10/20/30-session delivery history, delivery quantity/value comparison, up-day/down-day analysis, or verified OHLC peak series for U-Turn. |
| P3 Institutional evidence | INCOMPLETE | Bulk/block deals output is empty for this cohort and shareholding/pledge/FII/DII/insider-change evidence is not present in the report. Empty deals must remain “no disclosed deals” only if source coverage is verified. |
| P4 News and events | PARTIAL | News matched 10/17; 7 had no match. Upcoming events returned no rows; corporate actions returned no rows. Need keep source-coverage status separate from no-event/no-action result and verify exact official result timestamp before U-Turn use. |
| P5 Trap/surveillance | NOT IMPLEMENTED IN THIS REPORT | No ASM/GSM/ESM, Trade-to-Trade, Periodic Call Auction, price-band or corroborated multi-session risk evidence/exclusion ledger is present. |
| P6 Market/technical context | NOT IMPLEMENTED IN THIS REPORT | No Nifty/sector relative strength, SMA/RSI, trend/breakout/retest/closing-strength or liquidity/exit-readiness observations are present. |
| P7 Balanced decision | INCOMPLETE | The report has fundamental continuation statuses, but no transparent combined per-stock evidence classification, confidence, source-backed reasons and missing-data ledger across P2–P6. U-Turn remains optional research only and must not be a gate/trade signal. |
| P8 Live shadow validation | PARTIAL | One successful manual Morning shadow run, including real report/artifact/Telegram evidence. Need EOD and next-session cycle validation; no backtesting. |

## P1 defect found and ECMS-only correction

In this run, `ECMSFreeSourcesEvidenceStatus` contained literal `NAN` for records where the provider's `FreeSourcesStatus` was missing. This is a pandas missing-value normalization bug in ECMS reporting, not evidence that free-source collection ran or failed.

An ECMS-only correction was committed on the isolated branch `fix/ecms-p1-free-source-nan-status`:
- Normalize pandas NA/NaN/None to an empty status before deriving the ECMS evidence label.
- Preserve explicit statuses such as `DISABLED`.
- Do not manufacture an observation or change the shared provider.
- Add regression tests for missing and explicit-disabled statuses.

This correction is isolated and is **not merged to main**. It must pass ECMS CI before any review/merge.

## Ordered next work

1. Finish P1: validate the isolated NA-status fix; investigate why all metrics still use FY 2026-03-31 and why quarterly cash-flow periods are unavailable for most symbols; keep stale/unverified rows in WAIT.
2. Complete P0's EOD comparison and next-session cache/snapshot proof.
3. Implement P2 in an ECMS-only research layer: official daily OHLCV and delivery evidence, explicit session alignment and source/coverage ledger; preserve the U-Turn 20-session pre-result OHLC requirements.
4. Then P3, P4 source coverage, P5 surveillance, P6 technical context, P7 balanced labels, and P8 live shadow review in order.

No production selection changes are authorized by this audit. All missing, partial, stale, ambiguous or unverified inputs remain explicit; none is silently treated as a negative signal or as verified quality.
