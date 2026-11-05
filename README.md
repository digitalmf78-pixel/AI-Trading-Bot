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


## Optional Upstox fundamentals fallback

Set the repository Actions secret `UPSTOX_ACCESS_TOKEN` to enable the optional provider fallback in the NSE workflow. The scanner uses each candidate ISIN and requests annual consolidated income, balance-sheet, and cash-flow statements from the [Upstox Fundamentals API](https://upstox.com/developer/api-documentation/announcements/company-fundamentals-api/).

The fallback fills only missing Revenue Growth, Profit Growth, and Operating Cash Flow values when all three statement sources report the same annual period. It records per-metric provenance in `ProviderMetricSourcesJSON` and an Upstox status in provider diagnostics. It does not replace existing/manual values, loosen shortlist thresholds, or mark provider data as official XBRL evidence. The NSE XBRL audit remains the verification gate. If the token is absent or rejected, the run continues and records the reason without logging the token.
