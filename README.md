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
