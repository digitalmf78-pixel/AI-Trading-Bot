NSE V8 Company Announcements Parser Patch

Purpose
- Fix strict XML parse failures such as: "unclosed token" on large NSE RSS feeds.
- First use the normal XML parser. If the document is truncated/malformed, recover only individually well-formed complete <item> blocks.
- Mark recovered feeds as "partly available" so the report does not imply the entire feed was clean.
- Skip malformed/incomplete items; never synthesize announcement evidence.

Files
1. news_catalyst.py — full replacement based on issuer-aware version.
2. test_news_catalyst_parser.py — parser regression tests.
3. test_news_catalyst_matching.py — preserve issuer-matching regression tests.

Validation
Run in the repository root:
  python -m py_compile news_catalyst.py test_news_catalyst_parser.py test_news_catalyst_matching.py
  python -m pytest -q test_news_catalyst_matching.py test_news_catalyst_parser.py

Expected focused result: 9 passed (5 issuer matching + 4 parser tests).
This does not claim that the live NSE feed is available or that the entire V8 workflow is passing. After committing, run NSE Data Test and inspect the logs for the parser warning/status.

Do not replace volume_gainer.py, delivery_filter.py, sector_data.py, or v8_layers_14_41.py with this patch.
