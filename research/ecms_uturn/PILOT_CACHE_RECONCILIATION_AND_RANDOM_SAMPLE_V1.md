# U-Turn V1 — Cache Reconciliation and Random Source-Verification Sample

**Date:** 2026-11-17  
**Scope:** Isolated research branch only. Shared NSE V8 cache read-only. No production ECMS changes.

## 1. Correction: pilot event-study results are provisional pending a same-cache gate

Two successful GitHub workflows produced inconsistent pre-result-window coverage:

- Event-study run [#44063268302](https://github.com/digitalmf78-pixel/AI-Trading-Bot/actions/runs/44063268302) reported 20/20 pre-result sessions for INFY, ACI and AARTIIND, 606 symbol-session OHLCV rows and 202 sessions.
- Read-only audit run [#44063268268](https://github.com/digitalmf78-pixel/AI-Trading-Bot/actions/runs/44063268268) reported only 13/20, 14/20 and 13/20 verified sessions, respectively.

The audit parser was prematurely rejecting a session whenever the cache filename index returned more than one candidate file, before checking whether exactly one of those files contained the requested symbol's valid CM/STK/EQ row. The event-study parser instead read candidate files and filtered symbol rows. This explains a likely parser inconsistency, but the outputs must not be treated as reconciled until the same-run check passes.

### Fix applied

- The strict audit now examines every candidate file for the exact symbol/session and accepts only one verified matching row; zero or multiple valid matches remain WAIT_FOR_DATA.
- The strict audit now records its peak date and high.
- The U-Turn workflow now runs the strict audit and event-study in the same job and restored cache snapshot, then compares 20-session coverage, peak date and peak high for every pilot symbol.
- A fail-closed consistency gate blocks the workflow if the two parsers disagree.

**Until this gate passes, all previously reported 21/63/126-session returns, zone touches and ACI target observations are provisional and should not be used as strategy evidence.** The earlier report remains as an archived run output, not a final validated result.

## 2. Reproducible random source-verification sample

The cache audit found:
- 906 symbols in the fundamental-metrics universe.
- 237 rows passed the seven-metric populated-field and per-metric-provenance metadata gate.
- This gate does not verify every metric's underlying XBRL fact, and does not establish annual diluted EPS eligibility.

A reproducible five-symbol sample was drawn from the sorted 237-symbol candidate set using random.Random(20261117).sample(..., 5). All five selections are retained; no replacements are made after observing EPS outcomes.

Selection order:
1. UNITDSPR
2. INSPIRISYS
3. BORANA
4. KEYFINSERV
5. JSWSTEEL

See [RANDOM_SOURCE_VERIFICATION_SAMPLE_V1.csv](RANDOM_SOURCE_VERIFICATION_SAMPLE_V1.csv) for the complete record and source URLs.

### Findings

| Symbol | Annual diluted EPS FY25 → FY26 | Result |
|---|---:|---|
| UNITDSPR | ₹22.28 → ₹25.89 | No EPS decline; official issuer audited consolidated results |
| INSPIRISYS | ₹8.01 → ₹10.35 | No EPS decline; official NSE annual report and result filing |
| BORANA | ₹20.14 → ₹24.35 | No EPS decline; standalone only; security identifier mismatch blocks price study |
| KEYFINSERV | Not verified | WAIT_FOR_DATA; no official annual diluted EPS pair accepted |
| JSWSTEEL | ₹14.32 → ₹91.25 | No EPS decline; official NSE consolidated XBRL. FY26 EPS includes a material exceptional gain, retained as disclosed rather than adjusted |

Three symbols have a usable official annual diluted EPS pair and matching basis for a source-only check (UNITDSPR, INSPIRISYS, JSWSTEEL). BORANA's EPS values appear in the official NSE audited standalone results, but the PDF header's ISIN (INE16SF010106) differs from the NSE security master ISIN (INE16SF01016); therefore do not use BORANA in price event-study until the identity discrepancy is resolved. KEYFINSERV remains a failed-data sample; third-party/basic EPS must not be substituted.

**Important:** This random draw produced no verified EPS-decline case. It must remain unchanged; do not replace stocks to manufacture a positive/negative case mix. It is a source-verification pilot, not yet an event-study sample. A broader random draw or stratified design would need to be predeclared before a later research batch.

## 3. Two-sided cache context is not the U-Turn valuation test

The read-only audit found 237 rows with complete metric fields/provenance metadata and generated descriptive RSI/SMA/volume context for those rows. The summary explicitly states that underlying metric values are not individually verified and the bottom-side valuation zone was not run because verified annual diluted EPS and corporate-action-adjusted peak windows were unavailable.

These descriptive labels (NEUTRAL, MOMENTUM_STRONG, STRETCHED, WEAKENING, OVEREXTENDED) are not signals, and cannot be promoted to U-Turn outcomes.

## 4. Next acceptance gates

1. Same-run strict cache/event-study consistency gate must pass for the original three-symbol pilot.
2. Independently verify official NSE session calendar and result announcement timing for the five random sample names.
3. Reconcile each selected security's ISIN and corporate actions before price comparisons.
4. Verify annual diluted EPS from audited official statements, including continuing/discontinued operations treatment and consistent standalone/consolidated basis.
5. Only then run a new event-study. Keep all data failures and no-decline controls; do not alter the random sample after results are known.

No entry/exit simulation, P&L, buy/sell signal, Volume Gainers integration or production changes are part of this work.
