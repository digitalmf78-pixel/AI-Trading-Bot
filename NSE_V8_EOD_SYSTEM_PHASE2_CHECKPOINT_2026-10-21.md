# NSE V8 EOD System — Phase 2 Checkpoint

**Date:** 2026-10-21  
**Status:** Patch built and local regression-tested; **not deployed to GitHub**.

## Implemented in this patch

1. Preserves the existing official NSE Main Board / security-type validation.
2. Preserves latest-valid-EOD retrieval and the existing five-distinct-session delivery filter. Every one of the five sessions must be >=60.00%; below 60.00% rejects; missing sessions wait.
3. Keeps the 20-session average traded-value liquidity gate at the configured ₹5 crore threshold and applies it before RVOL ranking, as specified in the user's latest EOD sequence.
4. Adds a Fundamental Strength gate before RVOL/technical ranking. It requires source, source URL, as-of date, revenue/profit growth, ROE, ROCE, debt/equity, interest coverage, operating cash flow, free cash flow, earnings-quality status, and valuation status.
5. Fundamental thresholds are explicit configuration. They are intentionally shipped as `null` instead of inventing user-approved criteria. Missing metrics or unconfigured thresholds => `WAIT_FOR_DATA`; configured threshold failure => `REJECT`.
6. Preserves the existing sector and news/corporate-event modules.
7. Adds a portfolio-risk / position-sizing gate with explicit account equity, risk budget, stop-distance, total exposure, and sector exposure settings. Missing/unverified risk settings => `WAIT_FOR_DATA`.
8. Final EOD shortlist is capped at four; fewer than four or an empty/cash-only outcome is allowed.
9. Adds stage-labelled passed/rejected/wait reports, fundamental and risk reports, technical report, and `v8_final_shortlist.csv`.
10. Makes the final layer robust when upstream gates produce zero eligible candidates.
11. Adds targeted regression tests to the scheduled EOD workflow.

## Important activation requirement

The committed input templates intentionally contain no financial records and no approved thresholds. Until verified metrics are supplied in `data/inputs/fundamental_metrics.csv`, approved thresholds are entered in `data/inputs/fundamental_thresholds.json`, and verified portfolio risk settings are entered in `data/inputs/risk_config.json`, stocks must remain `WAIT_FOR_DATA` and the final shortlist should be empty. This is deliberate fail-closed behaviour, not a claim that the data feed is already automated.

## Local test results

- Python compile check: PASS.
- Targeted pytest suite: **37 passed**.
- Existing V8 regression suite: **27 passed**.
- Sector/news/cache unittest suite: **39 passed**.
- Empty eligible-universe smoke test: PASS; empty final-shortlist CSV is still written.

These are local tests against the patch files. A fresh GitHub Actions run is still required after applying the patch. No GitHub repository files were changed by creating this ZIP.

## Existing data freshness note

The latest supplied Actions/report evidence used EOD 2026-10-19 because Bhavcopy requests for 2026-10-20 and 2026-10-21 returned HTTP 404 in that run. Do not label that report as 2026-10-21 market data.
