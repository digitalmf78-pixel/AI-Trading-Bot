# NSE V8 — Cache Basis Persistence Fix (2026-10-30)

## Finding addressed
The provider diagnostics can report a newly fetched basis (for example `ANNUAL_FALLBACK`) while the cache row remains `LEGACY_CACHE_BASIS_UNKNOWN`. This happens when an existing row already contains some metric values: the collector preserves those values and does not replace the row-level calculation basis, because the row may contain a mixture of old and newly fetched metrics.

That preservation is correct, but the cache previously lacked separate fields to persist the provenance of only the newly fetched values.

## Change
Adds the following cache columns:
- `ProviderFetchCalculationBasis`
- `ProviderFetchQuarterlyAlignmentReason`
- `ProviderFetchIncomePeriodsUsed`
- `ProviderFetchCashFlowPeriodsUsed`
- `ProviderFetchBalanceSheetPeriod`
- `ProviderFetchedMetrics`
- `ProviderFetchedAtUTC`

When a fetch fills missing metrics, the fetch-level provenance is persisted separately. For a mixed legacy row, `MetricCalculationBasis` remains `LEGACY_CACHE_BASIS_UNKNOWN`; it is never promoted to `ANNUAL_FALLBACK` or `QUARTERLY_YOY_TTM` unless the entire row is provider-owned and refreshed as one coherent set.

This preserves existing values and avoids falsely assigning one calculation basis to mixed-period/mixed-origin metrics. Existing 30-day refresh behavior is unchanged.

## Tests
- Provider tests: 10 passed.
- Related fundamental shortlist/alignment, cache persistence, and official filing tests: 33 passed combined.
- Python compile check: passed.

## Scope / limitations
- Local patch only; not pushed to GitHub.
- No live NSE/Yahoo request was made.
- Does not independently verify official filing data or recalculate legacy metrics.
- No changes to Master Specification, RVOL, Delivery A/B, liquidity, valuation logic, or 30-day refresh interval.
