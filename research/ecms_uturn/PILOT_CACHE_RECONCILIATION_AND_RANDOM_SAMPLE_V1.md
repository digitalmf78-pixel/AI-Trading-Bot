# U-Turn V1 — Cache Reconciliation and Random Source-Verification Sample

**Date:** 2026-11-17  
**Scope:** Isolated ECMS research branch only. Shared NSE V8 cache read-only. No production ECMS changes.

## 1. Reconciliation — resolved for the three-stock pilot

Earlier event-study and strict-audit workflows disagreed on 20-session coverage. Root causes were identified and corrected:

- Legacy NSE cache date fields include day-first formats; the strict parser now uses format-aware parsing rather than treating every value as month-first.
- The strict audit now uses filename date hints only to prune candidates, then verifies the actual table date and exact symbol/ISIN/CM-STK-EQ row.
- If multiple candidate files exist, it accepts only one candidate containing exactly one valid symbol row. Index-history or unrelated files are not mistaken for a stock bhavcopy.
- Parsed audit tables are cached during the read-only scan.
- Cache inventory is bounded to headers and sample rows rather than scanning every row in every file.

### Latest acceptance runs

- U-Turn event-study / same-run consistency gate: [run #44077735477](https://github.com/digitalmf78-pixel/AI-Trading-Bot/actions/runs/44077735477) — **SUCCESS**.
- Read-only cache audit: [run #44077339832](https://github.com/digitalmf78-pixel/AI-Trading-Bot/actions/runs/44077339832) — **SUCCESS**.
- The latest U-Turn artifact includes the strict audit, event-study, consistency gate, official calendar/corporate-action audit and read-only cache provenance.

Verified outcomes:
- INFY: 20/20 pre-result sessions; peak High ₹1,376.90 on 08-Apr-2026.
- ACI: 20/20 pre-result sessions; peak High ₹639.80 on 04-May-2026.
- AARTIIND: 20/20 pre-result sessions; peak High ₹512.40 on 29-Apr-2026.
- 60/60 strict OHLC session rows READY; 60/60 delivery rows matched.
- Latest post-result close rows: 3/3 READY.
- Both parsers agree on coverage, peak date and peak High for all three names.
- All three manifest windows exactly match weekday NSE equity sessions after excluding the official 2026 NSE equity holidays.

See [PILOT_OFFICIAL_CALENDAR_EVENT_TIME_AUDIT.md](PILOT_OFFICIAL_CALENDAR_EVENT_TIME_AUDIT.md) for official sources and the exact event-time caveat for ACI.

## 2. Pilot event-study interpretation

The original three-stock pilot is descriptive, not randomized:
- ACI is the only EPS-decline case. Its calculated zone was touched on 8 sessions, but no same-session zone touch met both delivery >=60% and RVOL >=1.5x.
- INFY and AARTIIND had no annual diluted EPS decline; the engine correctly withheld downside targets.
- Price-only returns and gross cash-dividend-inclusive simple returns are reported separately. The latter adds gross cash dividends without reinvestment, tax or fee adjustments; it is not an official total-return index.
- No entry/exit, position sizing, fees, slippage, stop-loss or P&L was simulated.

See [PILOT_EVENT_STUDY_V1_RESULTS.md](PILOT_EVENT_STUDY_V1_RESULTS.md).

## 3. Reproducible random source-verification sample

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

Three symbols have a usable official annual diluted EPS pair and matching basis for a source-only check (UNITDSPR, INSPIRISYS, JSWSTEEL). BORANA's EPS values appear in the official NSE audited standalone results, but the PDF header's ISIN (INE16SF010106) differs from the NSE security master ISIN (INE16SF01016); therefore do not use BORANA in a price event-study until the identity discrepancy is resolved. KEYFINSERV remains a failed-data sample; third-party/basic EPS must not be substituted.

**Important:** This random draw produced no verified EPS-decline case. It must remain unchanged; do not replace stocks to manufacture a positive/negative case mix. It is a source-verification pilot, not an event-study sample.

## 4. Two-sided cache context is not the U-Turn valuation test

The read-only audit found 237 rows with complete metric fields/provenance metadata and generated descriptive RSI/SMA/volume context for those rows. The summary explicitly states that underlying metric values are not individually verified and the bottom-side valuation zone was not run because verified annual diluted EPS and corporate-action-adjusted peak windows were unavailable.

These descriptive labels (NEUTRAL, MOMENTUM_STRONG, STRETCHED, WEAKENING, OVEREXTENDED) are not signals and cannot be promoted to U-Turn outcomes.

## 5. Remaining acceptance gates

1. Expand to a predeclared random or stratified event-study sample with adequate EPS-decline and no-decline representation; freeze universe, seed, eligibility and exclusions before looking at outcomes.
2. Preserve all missing-data and negative outcomes; never replace a name after seeing its EPS or price result.
3. Independently verify each new sample's annual diluted EPS, basis, units, result announcement session, ISIN and corporate actions.
4. Do not tune the 20-session peak window, ±2% zone, 60% delivery or 1.5x RVOL thresholds after seeing outcomes.
5. Keep all outputs research-only. Production ECMS integration requires separate explicit approval after the Volume Gainers tape test succeeds.

No buy/sell signal, entry/exit, P&L simulation, Volume Gainers integration or production changes are part of this work.
