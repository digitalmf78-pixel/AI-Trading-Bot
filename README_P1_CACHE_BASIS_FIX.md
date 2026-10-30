# NSE V8.0 — P1 Cache Calculation-Basis & Fetch Provenance Fix

**Baseline:** latest audited repository source checked out by workflow run `41018653976`, commit `61f301584503142da1514c123e889f5c028bf444`.

## Scope

This is an isolated P1 cache-provenance patch. It changes only:
- `fundamental_data_provider.py`
- `test_fundamental_data_provider.py`

It does **not** include Quarterly TTM calculation changes (P2). It does not change the master specification, RVOL, Delivery A/B, liquidity, fundamental thresholds, valuation logic, technical filters, Telegram, or workflow scheduling.

## What it fixes

1. Adds explicit `MetricCalculationBasis` and `QuarterlyAlignmentReason` fields to the persistent cache.
2. Adds fetch-level provenance fields: `ProviderFetchCalculationBasis`, `ProviderFetchQuarterlyAlignmentReason`, `ProviderFetchIncomePeriodsUsed`, `ProviderFetchCashFlowPeriodsUsed`, `ProviderFetchBalanceSheetPeriod`, `ProviderFetchedMetrics`, and `ProviderFetchedAtUTC`.
3. Existing cache rows without a calculation basis are migrated to `LEGACY_CACHE_BASIS_UNKNOWN`. The patch deliberately does not infer a basis from an old period date or `MetricPeriodAlignmentStatus`.
4. Existing manual/legacy values remain untouched. If a fetch fills missing fields in a mixed row, row-level basis stays `LEGACY_CACHE_BASIS_UNKNOWN`; the fetch provenance is stored separately.
5. `ProviderFetchedMetrics` lists only metric fields actually inserted into blank cache fields, not every non-empty field returned by the provider.
6. A fully provider-owned row receives row-level basis metadata.
7. Existing 30-day provider refresh behavior remains in place. When a stale provider-owned row is refreshed, old metric values and old basis/provenance metadata are cleared together before the new fetch.
8. In this P1 phase, the current aligned annual statements path is labeled `ANNUAL_ALIGNED_STATEMENTS`; otherwise the provider snapshot path is labeled `UNALIGNED_PROVIDER_SNAPSHOT`. Quarterly TTM is explicitly marked as not evaluated in this phase.

## Apply instructions

From the repository root, replace the two files with the same-named files in this ZIP. Do not replace other project files. Commit/push the patch through the normal repository workflow, then inspect the next GitHub Actions run and its reports before proceeding to P2.

Do not edit the master specification. Do not commit secrets.

## Validation performed locally

- `test_fundamental_data_provider.py`: **7 passed**.
- Related regression suites (provider, shortlist/alignment, cache persistence, official filings, fundamental filter/fail-closed, pipeline order, liquidity, Delivery fallback and Delivery rule): **70 passed**.
- `python -m py_compile fundamental_data_provider.py`: PASS.
- The existing annual-alignment and stale-provider refresh tests are included in the related suite.

This ZIP is a local patch artifact only. It has **not** been pushed to GitHub or deployed in Actions. Live provider/network behavior was not tested by this local test run.
