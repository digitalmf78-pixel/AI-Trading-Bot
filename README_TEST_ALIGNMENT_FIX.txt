NSE Swing Trading V8.0 — Sector/API Test Alignment Fix

This patch addresses the five test issues in the uploaded repository ZIP while preserving the existing conservative sector-mapping policy.

Files to replace in the GitHub repository (replace the entire file contents):
1. sector_data.py
2. test_sector_mapping_patch.py
3. test_nse_official_index_api.py

Changes:
- The official Nifty Indices ASP.NET endpoint now receives the JSON request body as serialized `data`, matching the endpoint's expected request contract and the regression test.
- The AMJLAND sector-mapping test now supplies explicit reviewed classification evidence (`REALTY`). The ticker alone is not treated as evidence; the production logic still does not guess a sector from a symbol.
- The three old `test_nse_official_index_api.py` tests expected a different NSE API/function (`_history_from_nse_indices_api`) that is not implemented or used in the current repository. They have been replaced with tests for the current `_history_from_niftyindices_api` endpoint and current response format.

Validation performed locally:
- `python -m py_compile sector_data.py test_sector_mapping_patch.py test_nse_official_index_api.py` — PASS
- `python -m unittest discover -v` — 33 tests PASS

Important:
- This is local validation only. GitHub Actions has not yet verified the replacement files.
- Do not mark sector history complete merely because tests pass. Real feeds may still be blocked or unavailable; missing data must remain missing and downstream status should remain WAIT_FOR_DATA.
- Preserve the project delivery gate: five distinct valid sessions required; AvgDelivery5D >= 60.00% passes; below 60.00% rejects; fewer than five valid sessions => WAIT_FOR_DATA.
