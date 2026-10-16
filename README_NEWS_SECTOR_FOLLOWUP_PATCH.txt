NSE V8 NEWS + SECTOR FOLLOW-UP PATCH
Prepared from the uploaded repository and the latest logs dated 2026-10-16.

FILES (full replacements)
1. news_catalyst.py
   Fixes NSE RSS timestamps with no timezone. Values such as "16-Oct-2026 20:06:48"
   are treated as India exchange time (Asia/Kolkata), then normalized to UTC. Explicit
   timezone-bearing timestamps retain their explicit timezone. This addresses the log
   where all 20 financial filing entries were incorrectly rejected as after-window.

2. sector_data.py
   Adds parsing for an explicit `basicIndustry` value embedded in the official NSE
   quote HTML JSON, in addition to visible Basic Industry text. It does not guess a
   sector from a ticker or company name. If the official response contains no explicit
   classification, the candidate must remain WAIT_FOR_DATA.

3. test_v8_regression.py
   Adds regression checks for the NSE local-time parsing and embedded official JSON
   Basic Industry extraction. Existing V8 tests and delivery rules are preserved.

VALIDATION
- Run: python -m py_compile news_catalyst.py sector_data.py test_v8_regression.py
- Run: python test_v8_regression.py
- Then commit to GitHub and run the NSE Data Test workflow.
- A local test pass does not prove live NSE feeds provide the data; verify the new
  workflow logs for date_valid/after_window/issuer_matches and sector mapping statuses.

IMPORTANT
- Delivery gate is unchanged: AvgDelivery5D >= 60.00% passes; below 60.00% rejects;
  insufficient five-session evidence remains WAIT_FOR_DATA.
- No sector mapping is force-filled. A live API 403 or absent explicit Basic Industry
  can still leave some symbols WAIT_FOR_DATA; the new parser only helps when the official
  HTML response actually contains the field in embedded JSON.
