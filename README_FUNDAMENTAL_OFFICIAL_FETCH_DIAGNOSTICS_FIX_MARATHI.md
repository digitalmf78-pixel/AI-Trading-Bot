# NSE V8 Fundamental Official Filing Fetch Diagnostics Fix — 2026-10-23

## What changed
- Fetches NSE corporate announcements in bounded 30-day windows rather than one large 450-day request. This reduces the risk that a long request returns an incomplete/empty payload.
- Retains successful windows if another window fails. If every request fails and no filing rows were collected, the fetcher raises a clear error so the existing cache fallback can run.
- Adds `fetch_summary` diagnostics: requested date range, number of windows attempted/failed, total announcement rows, financial-result subjects, rows with dates, rows with parsed financial period ends, and matched filing count.
- Records `LIVE_FETCH_SUMMARY`, `LIVE_FETCH_PARTIAL`, and a detailed `LIVE_FETCH_EMPTY` reason in `outputs/v8_official_publication_date_verification.csv`.
- Supports NSE announcement wording containing “ended on” when parsing an explicit financial period end.
- Continues to require an exact symbol + explicit financial period end + publication date on or before the EOD cutoff. It does not infer a period end from AsOfDate or fabricate a publication date.
- Does not change Delivery A/B, RVOL, ₹2 crore Liquidity, or other pipeline rules.

## Files in this patch
- `fundamental_official_filings.py` (replace)
- `test_fundamental_official_filings.py` (replace)
- `TEST_RESULTS_FUNDAMENTAL_OFFICIAL_FETCH_DIAGNOSTICS_2026-10-23.txt`

## Local checks
- Targeted tests (official filings, provider, fundamental filter, delivery fallback, liquidity, pipeline order): 41 PASS
- `test_v8_regression.py`: 27 PASS
- Python compile check for fundamental provider/filter/official filings: PASS
- Live NSE API was not called in this local test run; actual publication-date verification must be confirmed from the next GitHub Actions report.

## Apply
Copy/replace only the two Python files at the same paths in the repository. Commit and push, then run the `NSE Data Test` workflow. Inspect `outputs/v8_official_publication_date_verification.csv` in the report artifact. The new summary counts will help distinguish endpoint/network issues from announcement-description parsing issues.
