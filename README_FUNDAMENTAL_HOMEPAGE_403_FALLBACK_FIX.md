# NSE V8 Fundamental Official Filing — homepage 403 fallback patch

## What this fixes
- The official NSE homepage request is now a best-effort cookie warm-up.
- If the homepage returns HTTP 403 or raises an exception, the code still attempts the official NSE corporate-announcements API.
- The API response must still pass HTTP status and schema validation. If the API itself fails or no exact symbol + financial-period match is found, records remain UNVERIFIED; no dates are invented.
- No changes to RVOL, Delivery A/B, liquidity, technical, news, risk, or ranking criteria.

## Files to replace
Copy these two files to the same paths in the repository:
- `fundamental_official_filings.py`
- `test_fundamental_official_filings.py`

Do not overwrite the whole repository.

## Local validation
- Fundamental provider / official filings / fundamental filter tests: 23 PASS
- Python compile check for `fundamental_official_filings.py`: PASS
- Live NSE endpoint: not tested here. GitHub Actions must confirm whether the official API itself is accessible.
