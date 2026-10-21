# NSE Swing Trading V8.0 — Audit & Phase 1 Patch Note

**Audit date:** 21 October 2026  
**Repository:** `digitalmf78-pixel/AI-Trading-Bot`  
**Commit confirmed from Actions checkout log:** `0c4c21923bf450724c6a9dac83495c35450aa126`  
**EOD data used by this run:** `2026-10-19` (newer Bhavcopy requests returned HTTP 404; run used cached/latest available data).

## A. Confirmed live-run sequence

The uploaded GitHub Actions log shows this order:
1. Main-board universe and five-session daily Delivery gate.
2. `303` stocks passed the gate; each of the five valid sessions must be `>=60.00%`.
3. `299` had complete volume history for the next stage; `4` remained `WAIT_FOR_DATA`.
4. RVOL Top 20 was selected.
5. Liquidity filter was then applied to those 20 rows, requiring 20-session average traded value `>= INR 5 crore/day`.
6. `1` passed liquidity and `19` failed.
7. Technical candidate check showed `0/1` passed the core technical setup; EOD candidate remained `WAIT_FOR_DATA`.

## B. Source ZIP versus Actions log

The supplied `AI-Trading-Bot-main(6).zip` places liquidity before RVOL Top 20 and writes `outputs/v8_liquidity_first_audit.csv`. The Actions log instead shows liquidity after RVOL Top 20 and writes `outputs/v8_liquidity_top20_audit.csv`. These artifacts therefore do not represent the same selection-pipeline order. The included Phase 1 patch changes the source ZIP's liquidity placement to match the observed run-log sequence, keeps the ₹5 crore threshold unchanged, and adds an ordering regression test.

## C. Liquidity threshold facts from the 20-row audit

- `>= ₹5 crore`: **1/20** pass.
- `>= ₹1 crore`: **1/20** pass.
- Between ₹1 crore and ₹5 crore: **0/20**.
- Therefore, lowering the threshold from ₹5 crore to ₹1 crore would not add a stock to this specific Top 20. This is not a claim about all 303 delivery-qualified stocks; the available report does not contain a verified 20-day traded-value figure for every one of those 303.
- XPROINDIA is the one liquidity pass (`AvgDailyTradedValue20D` ≈ ₹6.75 crore, RVOL ≈ 7.36x, `AvgDelivery5D` ≈ 69.088%), but it had no clear breakout/pullback setup, bearish trend/underperformance signals, `News=NO_DATA`, and final status `WAIT_FOR_DATA`. Not a BUY signal.

## D. Fundamental / cash-flow coverage

The delivery EOD audit has **no columns** for Fundamental Quality, Operating Cash Flow, or Free Cash Flow. This means the supplied artifacts cannot establish the financial-screening status of the 303 Delivery-qualified stocks. The attached `fundamental_cashflow_coverage_303.csv` marks these as `NOT_PRESENT_IN_DELIVERY_EOD_AUDIT`; it does **not** claim the companies lack such data. A sourced financial-data retrieval and validation stage is required before applying thresholds. Missing data must remain `WAIT_FOR_DATA`, not PASS.

## E. Patch scope and validation

Included files in the patch ZIP:
- `volume_gainer.py` — liquidity gate placed after RVOL Top 20, before technical analysis; threshold stays ₹5 crore.
- `test_liquidity_filter.py` — liquidity rule tests.
- `test_selection_pipeline_order.py` — ordering regression test.
- `.github/workflows/nse-test-scheduled.yml` — invokes the added selection-order test.
- `README_SELECTION_PIPELINE_PHASE1_MARATHI.txt` — Marathi application notes.

Fresh local validation performed here: Python compilation passed; focused Liquidity + Pipeline-order tests: **7 passed**. This does not replace a GitHub Actions run after the patch is applied.

## F. Safe next action

1. Apply the patch files to the matching repository paths.
2. Run GitHub Actions and confirm the new run produces `v8_liquidity_top20_audit.csv` with the expected order and passes the regression test.
3. Do **not** change the ₹5 crore threshold based on this Top 20 alone.
4. Implement Fundamental + Operating Cash Flow + Free Cash Flow only as a separate phase after selecting a verified financial data source, defining explicit thresholds, and testing missing/stale data behavior.

**Production status:** This audit has not changed GitHub. The patch is prepared for manual application and must be verified by a new Actions run.
