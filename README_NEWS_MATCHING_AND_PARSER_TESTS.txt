NSE V8 — News Matching + RSS Parser Test Workflow Patch

Purpose:
- Keep the separate GitHub Actions test workflow.
- Run both issuer-aware news matching tests and RSS parser regression tests.
- Avoid setup-python pip-cache failure when the repository has no requirements.txt or pyproject.toml.
- Do not run live NSE network tests in this focused test workflow.

Files:
1. .github/workflows/news-matching-tests.yml — full replacement for the existing focused workflow.
2. test_news_catalyst_parser.py — add to repository root.
3. test_news_catalyst_matching.py — preserve/replace repository root test with this version if it matches the current patch.
4. news_catalyst.py — included as reference/full replacement from the parser patch already prepared earlier. Do not replace it with an older version; use the parser-patched version that includes _rss_items partial-feed recovery and issuer matching.

GitHub steps:
- Replace .github/workflows/news-matching-tests.yml with the supplied workflow.
- Add test_news_catalyst_parser.py at repository root.
- Ensure test_news_catalyst_matching.py is at repository root.
- The parser patch's news_catalyst.py should already be the current version. Only replace it if it is the same newer version included here; do not revert to older code.
- Commit and run Actions > News Matching and Parser Tests.

Expected focused test result: 9 passed (5 issuer matching + 4 parser tests).
This expectation is not proof of GitHub success until the workflow actually runs. This focused workflow does not prove that the live NSE feed is complete, and does not replace the main NSE Data Test or the full V8 regression suite.
