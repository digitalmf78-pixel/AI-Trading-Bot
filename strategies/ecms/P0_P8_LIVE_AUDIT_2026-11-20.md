# ECMS P0–P8 live audit — 2026-11-20

**Audited run:** [Manual Morning run 44676678821](https://github.com/digitalmf78-pixel/AI-Trading-Bot/actions/runs/44676678821)  
**Artifact:** `ecms-volume-gainers-morning-44676678821`  
**Scope:** ECMS only. NSE V8 production workflow, code, providers, thresholds, caches and selection remain untouched. No historical backtesting.


## Governing data-source rule (P0 contract; mandatory for P1 onward)

This rule is fixed for ECMS and must be applied consistently in P1 and all downstream reports:

1. **Yahoo Finance via yfinance is the only fundamental data-collection provider.** Collect the seven agreed metrics from Yahoo Finance. Prefer the latest available quarterly values; if quarterly values are unavailable, use the latest available annual values and label them explicitly as `ANNUAL`. If neither is available, show `MISSING`. Never estimate, fabricate, or silently substitute another provider's value.
2. **NSE and BSE are verification-only sources.** Use official NSE/BSE filings and XBRL to verify Yahoo-sourced values, including reporting period, consolidated/standalone basis, audited/unaudited status, units, and calculation basis. NSE/BSE must not silently become alternate fundamental data providers.
3. **Keep collection and verification separate.** Yahoo data can be shown for research even when official verification is unavailable, but must remain explicitly unverified. Do not hide it, overwrite it with an unrelated source, or call it officially verified without matching evidence.
4. **Show freshness and period labels clearly.** Every metric must retain its own source period and basis. Label quarterly age as old (for example, `1Q_OLD`, `2Q_OLD`); label annual fallback as `ANNUAL`; missing values as `MISSING`. Never label an annual FY value as a current quarter.
5. **Verification outcomes remain distinct:** `OFFICIAL_VERIFIED`, `OFFICIAL_MISMATCH`, `OFFICIAL_NOT_AVAILABLE`, and `MANUAL_RECHECK_REQUIRED`. Research availability is separately labelled (for example, `YAHOO_RESEARCH_READY` or `YAHOO_RESEARCH_PARTIAL`). A Yahoo value alone never creates a fundamental PASS.
6. **No third-party fundamental fallback** (including Screener.in or other providers). Do not change shared provider code used by NSE V8; implement this policy only in ECMS-owned code, adapters, outputs, and tests.

P0 governance check: every ECMS report/cache row must preserve Yahoo source provenance and its own period/basis, while NSE/BSE verification status is stored independently. Any missing, stale, mismatched, or unverified value remains visible with an explicit label and cannot be silently promoted to verified.

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

Validation: ECMS CI passed on the branch (164 tests passed, including the new missing/disabled-status regression tests). The correction is isolated and is **not merged to main**.

## P1 policy enforcement work — 2026-11-20

Following the fixed P0 data-source contract, ECMS-only changes were made on this isolated branch:

- Fundamental metric rows are now emitted by the ECMS source-compilation layer only when their metric-level source is exactly `Yahoo Finance via yfinance`; cached values attributed to other providers are not surfaced as research metrics.
- Legacy manual Screener/other-provider observations are ignored. BSE manual filing rows are retained only as `BSE_OFFICIAL_FILING_VERIFICATION_EVIDENCE`, marked `OFFICIAL_VERIFICATION_EVIDENCE_PENDING` / `MANUAL_REVIEW_REQUIRED`; they cannot replace Yahoo values.
- Legacy cached secondary-source comparison payloads are suppressed in the ECMS comparison output.
- Both ECMS workflow jobs now set `V8_FREE_FUNDAMENTAL_SOURCES=false` explicitly. The ECMS scanner also forces this flag off inside its isolated workspace. Shared provider code was not changed.
- Annual Yahoo fallback now has an explicit `FundamentalDataFrequency=ANNUAL` and freshness labels such as `ANNUAL_3Q_OLD`, distinct from quarterly labels. The underlying period and age remain visible; annual data is not relabelled as a current quarter.
- Regression tests were updated for Yahoo-only source inclusion, third-party observation suppression, BSE verification-only status, and annual fallback freshness.

These are code changes under validation on the isolated branch only. They have not been merged to main and do not change NSE V8.

## Ordered next work

1. Continue P1: investigate why all seven metrics still carry FY 2026-03-31 (3Q_OLD) and why quarterly cash-flow periods are unavailable for most symbols. The provider diagnostics show 15/17 with no quarterly cash-flow periods, and most rows fall back to annual metrics with reason QUARTERLY_CASHFLOW_PERIODS_NOT_ALIGNED. Keep stale/unverified rows in WAIT; do not change the shared provider or force a PASS.
2. Complete P0's EOD comparison and next-session cache/snapshot proof.
3. Implement P2 in an ECMS-only research layer: official daily OHLCV and delivery evidence, explicit session alignment and source/coverage ledger; preserve the U-Turn 20-session pre-result OHLC requirements.
4. Then P3, P4 source coverage, P5 surveillance, P6 technical context, P7 balanced labels, and P8 live shadow review in order.

No production selection changes are authorized by this audit. All missing, partial, stale, ambiguous or unverified inputs remain explicit; none is silently treated as a negative signal or as verified quality.
