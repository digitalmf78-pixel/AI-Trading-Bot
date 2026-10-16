# NSE V8 — Nifty Healthcare API Diagnostic Patch

## Scope
Replace the repository's `sector_data.py` with this complete file and add `test_niftyindices_history_bootstrap.py`. No other V8 module is changed.

## Evidence from the latest run
The 2026-10-15 sector-history refresh had 19/20 exact-date sector closes. For the missing Nifty Healthcare close, the official Nifty Indices endpoint returned a full HTML document (`text/html`) with HTTP 200 instead of the expected JSON. The previous logs did not include the final response URL or redirect chain, so they could not distinguish an API route redirect from an access/WAF response.

## What this patch changes
- Uses explicit compact JSON request bytes and dedicated modern browser/AJAX headers for the historical API POST.
- Logs final response URL, redirect chain, server header, content type, and a short body preview when the endpoint returns HTML/non-JSON.
- Preserves the existing retry after refreshing the official historical-data page.
- Fails closed: it does not invent or carry forward a Nifty Healthcare close when the requested date is unavailable.
- Adds assertions for the outgoing JSON POST request in the mocked regression tests.

Official endpoint page: https://www.niftyindices.com/reports/historical-data

## Validation performed locally
- `python -m py_compile sector_data.py test_niftyindices_history_bootstrap.py` — PASS
- `python -m unittest -v test_niftyindices_history_bootstrap.py test_etf_underlying_mapping.py` — 6/6 PASS

The tests mock HTTP responses. They do **not** prove the live endpoint is fixed. This patch is specifically designed to capture the missing evidence from the next GitHub Actions run. After applying it, inspect the new log's `NON_JSON` lines for `final_url` and `redirects`. If it still returns HTML, keep Healthcare missing/`WAIT_FOR_DATA`; do not fabricate a close.

## Unchanged
- Delivery filter and its existing rules
- Master V8 specification and all other trading modules
- Sector membership rules and ETF mapping guardrails
