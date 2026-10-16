# NSE V8 News Issuer-Matching Diagnostic Patch

## Files
- `news_catalyst.py`: complete replacement for the uploaded current file.
- `test_news_issuer_matching.py`: focused regression tests for issuer matching.
- `.github/workflows/news-issuer-tests.yml`: separate GitHub Actions workflow so these tests run without replacing the existing NSE workflow.
- `README_NEWS_ISSUER_MATCHING_PATCH.md`: this note.

## What changed
1. Adds auditable logs for the NSE Equity Master schema/row count and the company name resolved for each candidate symbol.
2. Makes the Equity Master CSV header parsing tolerant of a UTF-8 BOM and header whitespace.
3. Checks text fields across each RSS item for issuer identifiers, while preserving the visible headline as the reported headline.
4. Allows an exact, whole-token match for a distinctive single-token registered company name of at least eight characters. A bare ticker word is still not accepted.
5. Adds regression tests for positive, negative, punctuation, and explicit ticker matches.

## What did not change
- Delivery gate remains `AvgDelivery5D >= 60%`.
- Setup gate remains BREAKOUT/PULLBACK when supplied.
- RSS headlines are not promoted to verified cause of a stock move.
- No 3+1 confirmation rules were changed.
- No news evidence is fabricated. A match still needs an issuer name or an explicit market-identifier form.

## Validation
Run locally:
`python -m unittest -v test_news_issuer_matching.py`

GitHub Actions: add `.github/workflows/news-issuer-tests.yml` from this ZIP. It runs the focused tests on workflow dispatch and relevant file changes, without replacing the existing NSE workflow.

This patch improves diagnostics and matching robustness. It does not guarantee that the official feed contains a filing for every candidate. If a candidate has no relevant filing in the lookback window, `0` official matches may be correct; the new logs should help distinguish that from a missing Equity Master mapping.
