# NSE V8 — Official Index History Fallback

## Why this patch exists

The latest workflow log shows the daily NSE index archive returning exact-date closes for 19/20 tracked indices. The legacy `niftyindices.com/Backpage.aspx/getHistoricaldatatabletoString` route redirects to a Sitefinity login page in GitHub Actions, so it returns HTML rather than JSON.

This patch adds a first fallback to NSE's historical index JSON endpoint:

- `GET https://www.nseindia.com/api/historicalOR/indicesHistory`
- Bootstrap page: `https://www.nseindia.com/report-detail/eq_security`
- Query fields: `indexType`, `from`, `to`
- Healthcare canonical request name: `NIFTY HEALTHCARE INDEX`
- Expected response keys include `data`, `EOD_INDEX_NAME`, `EOD_TIMESTAMP`, and `EOD_CLOSE_INDEX_VAL`.

References:
- NSE historical index data page: https://www.nseindia.com/reports-indices-historical-index-data
- NSE Indices Healthcare index page: https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-healthcare-index
- Independent endpoint contract reference: https://bennythadikaran.github.io/NseIndiaApi/api.html

## Files

- `sector_data.py` — complete replacement file. Tries the official NSE index-history API for only the missing exact-date sectors, then uses the existing Nifty Indices fallback only if data remains missing.
- `test_nse_official_index_api.py` — tests successful parsing, exact index identity validation, and non-200 fail-closed behavior.
- `test_niftyindices_history_bootstrap.py` — existing diagnostics tests retained.

## Validation performed here

- `python -m py_compile sector_data.py` — PASS
- `python -m unittest -v test_nse_official_index_api.py test_niftyindices_history_bootstrap.py` — 7/7 PASS

These are mocked/local tests; they do **not** prove that GitHub Actions can reach the live API. The new workflow must show a valid official JSON response and the exact-date sector count must reach 20/20 before the issue can be marked resolved. If the endpoint is blocked or returns invalid data, the code keeps the sector missing; it never synthesizes a close.

No delivery-filter thresholds, trade-selection rules, or unrelated modules are changed.
