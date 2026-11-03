# NSE V8.0 Audit Corrections — 03-Nov-2026

## Scope

This patch addresses two confirmed source-snapshot issues without changing the master specification, RVOL threshold, Delivery A/B thresholds, liquidity threshold, or any technical entry/exit calculation.

1. Unknown/legacy fundamental calculation basis could still receive a `PASS` assessment if its other fields looked complete.
2. The scanner applied `FundamentalShortlistStatus == PASS` as a hard downstream gate, despite the agreed sequence that fundamentals are collected for every Delivery A/B candidate and missing/unverified fundamentals are recorded rather than used to discard candidates at this stage.
3. The old Top-50 test still asserted a removed function and obsolete cap. It is replaced with tests for the current uncapped `RVOL > 1.5` selector.

## Changes

### A. Fail-closed calculation-basis assessment

`fundamental_shortlist.py` now allows only these explicit calculation bases for a fundamental assessment to proceed to threshold checks:

- `QUARTERLY_TTM_ALIGNED_STATEMENTS`
- `ANNUAL_ALIGNED_STATEMENTS`

Blank, `LEGACY_CACHE_BASIS_UNKNOWN`, `UNALIGNED_PROVIDER_SNAPSHOT`, and any unknown basis now produce `WAIT_FOR_DATA` with reason `METRIC_CALCULATION_BASIS_UNKNOWN_OR_UNSUPPORTED`. The provider-fetch basis is not substituted for the persisted metric basis because the cache may still contain older values.

### B. Fundamentals are metadata/ranking, not a rejection gate at this stage

`volume_gainer.py` now carries every Delivery Category-A candidate (Category B is a subset of A) into the existing liquidity/technical pipeline regardless of fundamental `PASS`, `FAIL`, or `WAIT_FOR_DATA`. Fundamental fields, assessment reasons, and `FundamentalScore` remain attached; rows are still ranked by available FundamentalScore and RVOL.

If fundamental collection or assessment throws an exception, Delivery-A candidates are retained with explicit `WAIT_FOR_DATA` metadata instead of being discarded. The Delivery A threshold remains unchanged.

### C. Current RVOL rule tests

`test_top50_rvol_selection.py` now tests the actual `select_rvol_above_threshold` function: all valid candidates with RVOL strictly greater than 1.5 are retained, no Top-50 cap is applied, and missing/WAIT/boundary values do not qualify.

### D. CI regression coverage

The scheduled workflow now runs the fail-closed fundamental tests and uncapped RVOL selection tests as part of the Delivery/Fundamental/Pipeline regression step.

## Snapshot audit findings (not automatic data corrections)

For the uploaded `fundamental_metrics.csv` snapshot (298 rows, EOD basis 2026-11-02):

- `LEGACY_CACHE_BASIS_UNKNOWN`: 173 rows
- `ANNUAL_ALIGNED_STATEMENTS`: 123 rows
- `QUARTERLY_TTM_ALIGNED_STATEMENTS`: 1 row
- `UNALIGNED_PROVIDER_SNAPSHOT`: 1 row
- With the stricter basis rule, assessment results: 235 `WAIT_FOR_DATA`, 55 `FAIL`, 8 `PASS`.

The 173 legacy-basis rows are not rewritten or deleted. The `ProviderFetchCalculationBasis` field is not proof that the already-stored metric values were calculated on that basis. Also, `FundamentalShortlistStatus=PASS` is an assessment against the current metadata and thresholds; it is **not** a claim that every Yahoo/yfinance metric has been reconciled to an official NSE filing. Official XBRL candidate facts remain separate and unverified.

A comparison of the five XML sample companies against the Yahoo/yfinance cache showed material differences for SETCO and NIRAJ. All five cache rows still have `MetricCalculationBasis=LEGACY_CACHE_BASIS_UNKNOWN`; therefore none of these cross-source comparisons is used to overwrite a value or declare an error. They remain reconciliation items. All XBRL facts remain candidate-only, not verified.

## Validation

The following local test batches passed after these changes:

- Fundamental shortlist, uncapped RVOL selector, pipeline-order and failure-path tests: 27 passed.
- Provider, fundamental filter, Delivery, Main Board, liquidity, XBRL diagnostic, risk and V8 regression tests: 75 passed.
- Cache workflow, official filing, news, sector, corporate-event, structural-resistance and valuation tests: 92 passed.
- Nifty history bootstrap, NSE official index API, RSI cache retest and Delivery fallback tests: 18 passed.

Total across the four non-overlapping batches: **212 passed**. Python compile checks for the modified source/tests also passed. The complete one-command `pytest -q` run timed out in this environment, so the 212 figure is the sum of the completed test batches, not a claim that a single full-suite invocation completed.

## Not changed

- Master specification files
- RVOL > 1.5 threshold / 20-session baseline
- Delivery Category A average >= 60%
- Delivery Category B each of five sessions >= 60%
- Main Board universe rules
- Liquidity threshold
- Fundamental cache values or historical snapshots
- Existing TTM arithmetic
- XBRL candidate facts and verification statuses

## Apply safely

This is a local patch against the uploaded source ZIP snapshot. The ZIP does not contain `.git` metadata or a commit SHA. Compare/merge these files against the current GitHub `main` before applying. No GitHub push, merge, or deployment was performed.
