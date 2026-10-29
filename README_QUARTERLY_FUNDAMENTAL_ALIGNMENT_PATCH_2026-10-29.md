# NSE V8 Quarterly Fundamental Alignment Patch — 2026-10-29

## Scope
- Adds a quarterly-statement alignment path in `fundamental_data_provider.py`.
- Prefers aligned quarterly income statement, balance sheet, and cash-flow statement data when all three expose the same latest period end.
- Revenue and profit growth compare the latest quarter with the same quarter one year earlier (column 5).
- Annualizes quarterly ROE/ROCE by 4 for comparison with the existing annual-style thresholds; debt/equity uses the latest quarter balance sheet; OCF/FCF are latest-quarter cash-flow values.
- Falls back to the existing aligned annual statement path when quarterly statements are unavailable or not aligned.
- Adds a regression test verifying quarterly preference and same-quarter year-over-year growth.

## Safety / constraints
- Does not alter master specification, RVOL, Delivery A/B, or fundamental threshold rules.
- Does not mark official filing publication dates verified. Provider metric alignment is not official filing verification.
- Does not bypass `WAIT_FOR_DATA` when official verification or required values are missing.
- This patch does not yet replace the existing 30-day provider refresh policy with a precise new-quarter discovery mechanism. That requires a separate, tested cache-refresh change so stocks can reuse cache while detecting a newly published quarter.
- The patch is not applied to GitHub by this artifact; run tests and inspect the diff before applying.

## Tests
`python -m pytest -q test_fundamental*.py test_*cache*persistence*.py`
Result: 45 passed.
