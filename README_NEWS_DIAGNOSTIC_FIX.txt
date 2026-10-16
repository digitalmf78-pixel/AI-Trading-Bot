NSE V8 — NEWS DIAGNOSTIC / RSS PARSING FIX
==========================================

Replace only `news_catalyst.py` with the full replacement in this ZIP.
Do not replace `delivery_filter.py`, `sector_data.py`, or V8 strategy layers with this patch.

What this fixes:
1. Reads the NSE Equity Master CSV using UTF-8-SIG and normalizes BOM/whitespace in headers, so SYMBOL and NAME OF COMPANY can be detected.
2. Adds bounded, namespace-safe RSS field diagnostics (`_rss_debug_fields`) for titles, descriptions, links, and other RSS fields.
3. Reads RSS item/title/description/link fields independent of XML namespace prefixes.
4. Discovers RSS <item> nodes when the feed uses a default XML namespace.
5. Keeps the existing conservative issuer matching. It does not promote secondary news to primary evidence, does not invent headlines, and does not change the >=60% delivery gate or the 3+1 confirmation rules.

Local validation performed:
- Python compilation passed for news_catalyst.py and the focused tests.
- `pytest -q test_news_catalyst_parser.py test_news_catalyst_matching.py test_news_issuer_matching.py test_news_rss_diagnostics.py`: 18 passed.
- Smoke test confirmed a BOM-prefixed Equity Master maps AROGRANITE to Aro Granite Industries Limited.
- Smoke test confirmed a namespace-qualified RSS feed returns its title and publication date.

GitHub steps:
1. Open `digitalmf78-pixel/AI-Trading-Bot`.
2. Open `news_catalyst.py` and replace the entire file with the ZIP's file.
3. Commit changes.
4. Run the existing NSE Data Test workflow.
5. In fresh logs, inspect `[NEWS-DIAG] ISSUER_MASTER`, `OFFICIAL_FEED_SUMMARY`, `RSS_FIELDS`, and `SECONDARY_FEED_*`.
6. Upload the new workflow report/log ZIP so the live result can be verified.

Important:
This patch improves parsing and diagnostics but cannot guarantee the NSE RSS feed contains a relevant filing for every candidate. If issuer mapping is still 0 or feeds return no relevant items, keep `WAIT_FOR_DATA`. Local tests are not proof that the GitHub workflow passed.
