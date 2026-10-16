NSE Swing Trading V8.0 — Official News Matching Diagnostic Fix

Files:
- news_catalyst.py: complete replacement for the repository file
- test_news_official_feed_diagnostics.py: focused regression tests

What changed:
1. RSS item fields are read by XML local-name, including namespaced title/description/link fields.
2. The RSS parser collects item/entry nodes regardless of namespace.
3. Official matching can inspect explicit company/issuer/symbol fields where present, in addition to title and description.
4. Filing/announcement timestamp tags such as filingDate, filedDate, broadcastDateTime and submissionDate are recognized.
5. Official feed diagnostics now separate missing timestamps, records before the five-session window, and records after the EOD cutoff.
6. Explicit ticker forms such as NSE: SYMBOL, (SYMBOL), and SYMBOL.NS are tested against raw text before punctuation normalization. Bare ambiguous words (for example TECH) remain rejected.
7. Equity master CSV is read with utf-8-sig to tolerate a BOM.

Validation performed locally:
- Python compilation: PASS
- Existing News tests from the supplied repository: 18/18 PASS
- New focused tests: 5/5 PASS
- Combined News tests: 23/23 PASS

Important:
- These are local tests only; GitHub Actions has not yet verified this replacement.
- This patch does not fabricate news or force any candidate to PASS.
- If no issuer-matched official item exists in the allowed date window, the correct result remains NO_DATA / WAIT_FOR_DATA.
- Delivery gate remains AvgDelivery5D >= 60.00%; below 60 rejects; insufficient valid sessions remain WAIT_FOR_DATA.

GitHub steps:
1. Open news_catalyst.py in the repository.
2. Replace its entire contents with the included news_catalyst.py.
3. Add test_news_official_feed_diagnostics.py to the repository root.
4. Commit the changes.
5. Run the News tests and the main NSE workflow.
6. Upload the new workflow logs ZIP for verification.
