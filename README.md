# NSE V8 — Legacy Fundamental Cache Basis Migration (2026-10-30)

## Purpose
Safely mark old fundamental-cache rows that predate `MetricCalculationBasis` tracking.

## Behavior
- Missing/blank `MetricCalculationBasis` becomes `LEGACY_CACHE_BASIS_UNKNOWN`.
- Adds an explanatory `QuarterlyAlignmentReason` when that field is also blank.
- Preserves all existing metric values, source fields, filing metadata, and historical `MetricPeriodAlignmentStatus`.
- Does not infer quarterly or annual basis from `FinancialPeriodEnd`, publication date, or a legacy alignment flag.
- Does not convert unknown records into verified quarterly TTM records.
- New records continue to receive the basis assigned by the provider fetch logic.

## Files
- `fundamental_data_provider.py`
- `test_fundamental_data_provider.py`

## Validation performed locally
- Fundamental provider tests: 8 passed.
- Fundamental alignment/filter/fail-closed/official-filing/cache-persistence tests: 40 passed.
- Python compile check: passed.

## Important limitations
This is a local patch only; it has not been pushed to GitHub and has not been run against live NSE/Yahoo endpoints. It does not independently verify official filings or recalculate legacy financial metrics. Unknown legacy basis remains unknown until refreshed from a source that supplies a traceable calculation basis.

No changes to Master Specification, RVOL, Delivery A/B, liquidity thresholds, 30-day refresh interval, or downstream trading filters.


## Free-source fundamentals policy

- Official NSE integrated financial filings and XBRL are the primary verification source. A value is treated as officially verified only after it is reconciled with a dated filing and matching period/basis.
- Yahoo Finance accessed through `yfinance` is a secondary, no-token provider for candidate metrics and valuation snapshots. It can be delayed, incomplete, revised, or inconsistent; provider values remain unverified until the NSE filing audit confirms them.
- No paid provider token or paid data API is required by the scanner. Missing, stale, or conflicting figures remain visible as `WAIT_FOR_DATA` or a mismatch instead of being guessed or promoted.
- No shortlist threshold is weakened to compensate for missing source data. Review NSE XBRL and provider diagnostics when coverage is incomplete.

---

## Current authoritative rule addendum

The active 30-calendar-day NSE Delivery A/B screening rules agreed on 2026-11-07 are documented in [`NSE_V8_DELIVERY_AB_RULES_ADDENDUM_2026-11-07.md`](NSE_V8_DELIVERY_AB_RULES_ADDENDUM_2026-11-07.md). This addendum supplements the Master Specification; it does not replace or rewrite it.

## Current authoritative RSI rule addendum

The RSI informational-only / no-stock-rejection policy agreed on 2026-11-07 is documented in [NSE_V8_RSI_INFORMATIONAL_ONLY_RULES_ADDENDUM_2026-11-07.md](NSE_V8_RSI_INFORMATIONAL_ONLY_RULES_ADDENDUM_2026-11-07.md). RSI is reported to Telegram but cannot affect stock eligibility or any existing non-RSI filter.


## Delivery-first eligibility and RVOL classification (2026-11-07)

- **Delivery A OR B is the eligibility gate.** A stock qualifies when its Category A 30-calendar-day average Delivery is >=60.00%, or when every valid Delivery session in that window is >=60.00%. The existing minimum valid-report and point-in-time rules remain unchanged.
- **RVOL is calculated for the Main Board universe but its threshold is applied only as a classification after Delivery.** RVOL >1.5 is labelled `HIGH_RVOL_GT_1_5`; RVOL <=1.5 is labelled `LOW_RVOL_LE_1_5`; unavailable/invalid RVOL is labelled `WAIT_FOR_DATA`.
- **No stock that passes Delivery A or B is rejected or dropped because RVOL is <=1.5 or missing.** All unique Delivery-qualified stocks proceed to the existing liquidity check. Downstream technical analysis may use the RVOL value as an observation/setup input, but the RVOL threshold itself is not a pre-liquidity rejection gate.
- The EOD artifacts separately expose the complete Delivery A list, complete Delivery B list, complete A/B union with RVOL classification, high-RVOL candidates, low-RVOL Delivery candidates, and RVOL-WAIT candidates.
- The strict numeric boundary remains unchanged: exactly 1.50 belongs to the low-RVOL group; only values strictly greater than 1.50 belong to the high-RVOL group.
- The Master Specification is not modified by this addendum. No Delivery thresholds, liquidity thresholds, or unrelated downstream filters are changed.


---

## Hybrid Strategy — persistent working parameters (09-Nov-2026)

The current project scope, confirmed parameters, implementation order, Phase 1 code-audit findings, four independent watchlists, unresolved decisions and continuity instructions are recorded in:

**[NSE V8 Hybrid Strategy Master Parameters](NSE_V8_HYBRID_STRATEGY_MASTER_PARAMETERS_2026-11-09.md)**

Read this register before continuing project work. It is the persistent working reference for the Smart-Money Footprint + Accumulation + VCP + Breakout hybrid so the user does not need to repeat previously agreed decisions.

### Working priority
- Build **Potential Accumulation → Base/VCP Forming → Breakout Ready → Confirmed Entry** as four separate watchlists.
- Preserve the current Mainboard universe, 30-calendar-day Delivery A/B rules, RVOL informational classification, ₹1.5 crore liquidity minimum, fundamental enrichment/cache, RSI informational-only policy and all existing risk gates.
- Do not reject an early accumulation/base candidate solely because VCP or breakout is not yet present.
- Do not change Sector Strength, News/Catalyst or mandatory 3+1 during the initial hybrid phases. Preserve them for later integration.
- Pending thresholds (VCP contraction/base width/duration, Pocket Pivot formula, false-breakout buffer, retest window and other recorded open decisions) must not be guessed or silently turned into hard filters.
- The original `Pasted text(20261009-143842).txt` / `NSE SWING TRADING SYSTEM V8.0` Master Specification remains unchanged and authoritative. The hybrid register supplements it; it does not replace it.



## Hybrid strategy implementation status

The working decisions, confirmed thresholds, pending parameters and phase-by-phase implementation status are maintained in [NSE V8 Hybrid Strategy Master Parameters](NSE_V8_HYBRID_STRATEGY_MASTER_PARAMETERS_2026-11-09.md). The original Master Specification remains unchanged. Delivery Quantity observations are informational only and do not alter Delivery A/B eligibility.

- Delivery report integrity: the internal NSE report date is checked against the requested session before cached/downloaded data is accepted.

- Phase 2 Delivery Quantity observations: code integrated and validated by GitHub Actions (211 unit/data-audit tests + 31 V8 regression tests passed). Live NSE artifact/header verification remains a follow-up; missing data fails closed and never affects Delivery A/B eligibility.


- Phase 4 Potential Accumulation observations: a separate report now runs on the full Delivery A/B union before Liquidity. It records rolling price ranges, pivot/Higher-Low observations, Delivery >=60% price response and down/up-day volume context. It does not filter or score candidates. GitHub Actions validated 217 unit/data-audit tests and 31 V8 regression tests. Fixed-range base/VCP thresholds and watchlists remain pending.

- Phase 6 Early Trend observations: EMA20/44/50/200 values, distance and position now appear in the pre-Liquidity accumulation observation report. They are informational only and do not reject stocks below EMA200. Latest validation: 218 unit/data-audit tests and 31 V8 regression tests passed.

- Phase 5 VCP observations: three consecutive 20-session range/volume blocks and contraction/dry-up ratios now run before Liquidity on the Delivery A/B union. The <0.5x volume flag is observational only; VCP is not classified and does not gate candidates. Latest validation: 221 unit/data-audit tests and 31 V8 regression tests passed.

- Phase 7 integrity work: breakout/pullback, support/resistance and trend indicators now fail closed on missing or incomplete market sessions; original signal thresholds are unchanged. Liquidity duplicate rows/dates now WAIT_FOR_DATA. Latest CI: 239 unit/data-audit tests and 31 V8 regression tests passed.
- Phase 3 audit: fundamental cache and dated snapshots are persisted in-repo by the scheduled workflow. Collection remains after Liquidity pending the recorded boundary decision; XBRL value verification remains a separate non-gating sidecar.

- Four independent Hybrid watchlists are now emitted: Potential Accumulation and Base/VCP before Liquidity; Breakout Ready and Confirmed Entry after existing EOD gates. They are reporting-only and never feed back into candidate selection. Final EOD missing prerequisites now WAIT_FOR_DATA. Latest CI: 253 unit/data-audit tests and 31 V8 regression tests passed.

- Final EOD AD and ATR fallback now require complete 20-session data; mandatory 3+1 thresholds and portfolio risk controls were audited and preserved. Missing account/risk inputs remain WAIT_FOR_DATA. Latest CI: 257 unit/data-audit tests and 31 V8 regression tests passed.

- RVOL baseline now requires exactly 20 distinct prior sessions per symbol; duplicate/missing rows and invalid current volume return WAIT_FOR_DATA. Strict >1.5 classification is preserved and never rejects Delivery A/B candidates. Latest CI: 264 unit/data-audit tests and 31 V8 regression tests passed.

- Delivery Quantity, Accumulation and VCP source history now fail closed on duplicate report dates/rows, invalid quantities, missing price sessions and duplicate EOD rows. Current EOD values are reconciled without hiding duplicates. Latest CI: 273 unit/data-audit tests and 31 V8 regression tests passed.

- Accumulation ATR now requires complete OHLC input; selling-pressure volume averages require 20 valid non-negative volumes. Latest CI: 275 unit/data-audit tests and 31 V8 regression tests passed.

- Early Potential Accumulation watchlist now preserves the unique Delivery A/B union with explicit WAIT_FOR_DATA if its optional evidence engine fails. Latest CI: 276 unit/data-audit tests and 31 V8 regression tests passed.

- Breakout/Pullback and Support/Resistance now fail closed on invalid OHLCV candles, malformed history windows, duplicate candidates and missing required price columns. No unapproved retest or Pocket Pivot thresholds were added. Latest CI: 284 unit/data-audit tests and 31 V8 regression tests passed.

- Added a descriptive post-breakout retest observation report using existing V8 breakout definitions. It measures exact reference-level touches and post-breakout price/volume response without inventing a retest window or buffer; it is not an entry gate. Pocket Pivot remains pending exact approved formula. Latest CI: 291 unit/data-audit tests and 31 V8 regression tests passed.

- Pocket Pivot / repeated Support-Resistance audit: no Pocket Pivot detector or tolerance-clustered S/R zone-test counter currently exists. Existing 20/50/100/200-session exact extreme touch counts and confirmed pivots remain raw observations only; they are not zone confirmations. Formula/lookback/candle rules and zone/touch definitions remain unapproved, so no guessed signal or gate was added. See parameter register section 27.

- Base/VCP audit: retained the observational three-block (3×20-session) contraction and volume report; fixed-range base duration and final VCP thresholds remain unresolved. Hardened data integrity so non-finite prices/volume, invalid OHLC structure and duplicate candidate identities return WAIT_FOR_DATA. No scanner or entry gates changed. Latest CI: 295 unit/data-audit tests + 31 V8 regression tests passed.

- Base/VCP observations enhanced: rolling 20/50/100/200-session windows now include start/end dates, exact session count, average daily range and latest-close position; VCP reports contraction depth and whether price and volume contract together. These remain descriptive, not fixed-base/VCP classifications. False-VCP outcomes remain unevaluated until a forward horizon/failure definition is approved. Latest CI: 297 unit/data-audit tests + 31 V8 regression tests passed.
