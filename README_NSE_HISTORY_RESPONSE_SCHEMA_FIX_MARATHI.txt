NSE V8.0 — Historical Index API Response Schema Fix
Date: 20-Oct-2026

ROOT CAUSE
The current sector_data.py treated payload["data"] as a list only. NSE's historical index endpoint commonly returns rows under:
payload["data"]["indexCloseOnlineRecords"]
When "data" is a dictionary, the old code rejected the response as EMPTY_OR_INVALID_DATA before inspecting any rows. This explains why HTTP 200 responses could still yield zero fallback rows.

CHANGE
- sector_data.py now accepts the documented nested indexCloseOnlineRecords list.
- It remains backward-compatible with a direct payload["data"] list and alternate nested "data"/"records" lists.
- Diagnostic logs now print top-level keys, data type, and nested keys if the response is still empty/invalid.
- Index name, exact date range, and positive closing-value validation remain in place. No index close is inferred or fabricated.

TESTS RUN LOCALLY
- Python compilation: PASS
- unittest: 38 tests PASS across official index API, Sector/News, cache reconciliation and issuer matching
- pytest: 31 tests PASS (parser and V8 regression test selection)
- New regression test explicitly covers {"data": {"indexCloseOnlineRecords": [...]}}.

APPLY
1. Open the main repository digitalmf78-pixel/AI-Trading-Bot.
2. Replace sector_data.py with this ZIP's sector_data.py.
3. Replace test_nse_official_index_api.py with this ZIP's test file.
4. Add/replace README_NSE_HISTORY_RESPONSE_SCHEMA_FIX_MARATHI.txt.
5. Commit and manually run the NSE Data Test workflow.
6. Check logs for:
   [SECTOR][NSE_HISTORY] sector=...
   [SECTOR][NSE_HISTORY] fallback rows=... exact_date_sectors=...

IMPORTANT
Local tests validate parsing logic, not live NSE availability. If NSE still returns no records, the new diagnostic log will show the response shape. Delivery >=60% for each of the previous 5 valid sessions, 20-session traded value >= ₹5 crore, Volume/RVOL/Top 20, and other business rules are unchanged. No separate Delivery Watchlist files are included.
