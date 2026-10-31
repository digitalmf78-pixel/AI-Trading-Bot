# NSE V8 P2 — Quarterly TTM Cache Activation Fix

## Root cause identified from Run 41175756657

The deployed source already contains the quarterly TTM calculation path and the report schema contains the TTM audit columns. However, `collect_missing_fundamentals()` skips a candidate when all legacy `METRIC_COLUMNS` are populated. P1 cache rows therefore never call `_fetch_one()` for the new P2 quarterly calculation until their normal 30-day refresh becomes due. This leaves the TTM columns blank and the old P1 reason visible.

## Fix

- Adds `TTMCalculationAttemptedAtUTC` so each cached symbol gets a one-time P2 enrichment attempt without forcing the normal 30-day refresh.
- Fresh, complete P1 cache rows are fetched once for TTM enrichment when this marker is blank.
- When quarterly statements align and TTM is verified, existing Yahoo/provider-owned metrics are upgraded to the quarterly-derived values and their basis/provenance is updated.
- Manual or mixed legacy metric values are never overwritten. TTM audit values remain separate from those manual metrics.
- When quarterly TTM is unavailable, an explicit `UNAVAILABLE_ANNUAL_FALLBACK` or `WAIT_FOR_DATA` status and reason are stored, preventing the output from looking like an unattempted P1 row.
- The normal `V8_FUNDAMENTAL_REFRESH_DAYS=30` policy remains unchanged. Stale refresh clears the TTM audit columns, including the attempt marker, so the next refresh can recalculate.
- No changes to Master Spec, Delivery A/B, RVOL, Liquidity, thresholds, ranking rules, or technical filters.

## Files in this patch

- `fundamental_data_provider.py`
- `test_fundamental_data_provider.py`

Apply these two files over the current P2-enabled repository source. Do not replace the whole repository or revert the earlier P2 files.

## Local validation

- Python compile: PASS
- Focused Fundamental Provider / Alignment / Cache / Official Filing suites: included in combined test run
- Combined relevant regression tests: **106 PASS**

Tests include:
- fresh complete provider cache receives one-time TTM enrichment without waiting 30 days;
- quarterly verified metrics upgrade provider-owned cache rows;
- manual metric values and source remain unchanged while separate TTM audit values are retained;
- existing fundamental, cache persistence, official filing, delivery, liquidity, fail-closed, selection pipeline, and V8 regression tests remain passing.

## Deployment status

This is a local patch only. It has not been pushed to GitHub. Live provider execution and official filing verification must be checked in the next GitHub Actions run.
