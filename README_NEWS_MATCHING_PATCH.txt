NSE V8 — Issuer-aware News Matching patch

Files:
- news_catalyst.py (complete replacement)
- test_news_catalyst_matching.py (focused regression tests)

Fix:
- Bare ticker-word matches are no longer enough to assign a news headline to a stock.
- Match must contain the normalized registered issuer name (legal suffix differences allowed) or an explicit ticker form such as "NSE: SYMBOL", "SYMBOL.NS", or a parenthesized ticker.
- Google News queries prefer registered company name plus ticker when the NSE equity master is available.
- This specifically blocks unrelated "Akash Anand", "Akash Bhansali", Bharat Dynamics/AKASH missile, and Akash Ambani stories from being attributed to AKASH INFRA-PROJECTS LTD.
- Secondary headlines remain secondary evidence; this patch does not promote them to official/primary evidence.

Validation:
Run `python -m py_compile news_catalyst.py test_news_catalyst_matching.py`
Run `python -m pytest -q test_news_catalyst_matching.py`
Then run the repository's full Regression Test Suite and NSE Data Test in GitHub Actions.
Do not mark any stock BUY based on news matching alone.
