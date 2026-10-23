# NSE V8.0 — Fundamental Collection Stage Update
**Date:** 23 October 2026

## Approved selection sequence
1. NSE Mainboard eligible equity universe.
2. Calculate RVOL using today's volume divided by the average volume of the previous 20 complete trading sessions.
3. Keep every stock with `RVOL > 1.5`; no Top-20/Top-50 cap.
4. Create two independent Delivery categories using five distinct valid trading sessions:
   - Category A: five-session average Delivery % `>= 60.00%`.
   - Category B: every one of the five daily Delivery % values `>= 60.00%`.
   - Fewer than five valid sessions => `WAIT_FOR_DATA`.
5. Fundamental data collection for every stock in the union of Category A and Category B. Do not reject a stock at this stage because its fundamental metrics are weak, missing, or thresholds are not configured.
6. Existing liquidity, technical, news, sector and risk checks remain in place after the data-collection stage.
7. Strong-fundamental ranking/shortlisting is deferred to a later stage.

## Fundamental reports
- `outputs/v8_fundamental_report.csv` — all Category A/B union candidates with available fundamental fields, completeness, provisional score and data status.
- `outputs/v8_delivery_a_fundamentals.csv` — Category A candidates.
- `outputs/v8_delivery_b_fundamentals.csv` — Category B candidates.
- `outputs/v8_delivery_ab_combined_fundamentals.csv` — deduplicated union of both categories.
- `outputs/v8_fundamental_complete_data.csv`
- `outputs/v8_fundamental_partial_data.csv`
- `outputs/v8_fundamental_missing_data.csv`

Fundamental status is informational at this stage: `COMPLETE`, `PARTIAL_DATA`, or `MISSING_DATA`. `FundamentalAssessmentStatus` remains `NOT_SHORTLISTED_YET`. Provisional score/rank is emitted only when all six numeric ranking metrics are present.

## Data-source limitation
This patch reads the existing `data/inputs/fundamental_metrics.csv` and joins its available values to all eligible candidates. It does **not** invent missing fundamentals or automatically scrape/fetch company financials. If a symbol has no input record, it remains in the report with `MISSING_DATA`. An authenticated/approved financial-data provider or an official-source ingestion workflow must be configured separately to populate that CSV automatically.

## Verification
- `python -m py_compile *.py`: PASS.
- `python -m pytest -q test_*.py`: **138 passed**.
- Full workflow against live NSE endpoints was not verified in this environment because network/DNS access was unavailable.
- GitHub Actions deployment has not been performed from this chat; apply the patch in GitHub and upload the next logs/report artifacts for runtime verification.
