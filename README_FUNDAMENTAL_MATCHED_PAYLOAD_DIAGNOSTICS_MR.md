# NSE V8 Fundamental Official Filing — Matched Payload Diagnostics

## Why this patch
The 2026-10-24 run's `outputs/v8_official_fetch_diagnostics.csv` reported:
- NSE homepage warm-up: HTTP 403 (non-fatal)
- official API: HTTP 200
- payload items: 229,239
- financial-term matches: 1,983
- publication dates parsed / within date range: 1,983
- symbols parsed: 1,983
- period ends parsed: 0
- accepted rows: 0

The current diagnostic only recorded generic sample descriptions and did not expose the field names/values for matching rows. This patch adds:
- `APIRequestParams`
- `SampleFinancialResultMatches`
- `SampleMatchedItemKeys`
- `SampleMatchedItemFields`

These fields should show the actual NSE response schema and whether period end is in a structured field or announcement text.

## Safety / scope
- Diagnostics only. Existing record acceptance rules remain unchanged.
- No inferred publication dates, period ends, or filing URLs.
- No changes to RVOL, Delivery A/B, Liquidity, technical, news, sector, corporate-event, or risk filters.
- Candidates remain retained when official verification is unavailable; unverified rows do not become verified.

## Apply
Replace in GitHub:
1. `fundamental_official_filings.py`
2. `test_fundamental_official_filings.py`

Commit and run the existing NSE Data Test workflow. Then upload the new report ZIP. Inspect `outputs/v8_official_fetch_diagnostics.csv`, especially the new sample fields.

## Local validation
Run:
`python -m pytest -q test_fundamental_official_filings.py`
`python -m py_compile fundamental_official_filings.py`

Live NSE schema verification remains pending until a fresh workflow artifact is generated.
