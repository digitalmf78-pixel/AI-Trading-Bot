NSE SWING TRADING V8.0 — NEW SELECTION PIPELINE PATCH
Date: 2026-10-23

Approved order:
1. Official NSE Main Board universe (SME and ETF excluded).
2. Validate prior 5-session and prior 20-full-session volume history.
3. Calculate RVOL = current EOD volume / prior 20 full sessions' average volume.
4. Select Top 50 candidates by descending RVOL.
5. Produce two separate Delivery categories on the Top 50:
   A. AVG_DELIVERY_60: average Delivery % across five valid distinct sessions >= 60.00%.
   B. DAILY_DELIVERY_60: each of the five valid distinct sessions individually >= 60.00%.
   Category B is a subset of Category A. A stock can appear in both reports.
   Fewer than five valid session values => WAIT_FOR_DATA, never PASS.
6. Check fundamental evidence and rank stronger/verified PASS candidates first.
   A relative Fundamental Score (0-100) is calculated from available numeric metrics
   for ranking only; it does not override missing/stale evidence or existing configured
   fundamental PASS/REJECT checks.
7. Continue into the existing technical, news, sector, risk/reward, and final shortlist gates.

New/updated outputs:
- outputs/v8_primary_shortlist_top50.csv
- outputs/v8_delivery_categories_audit.csv
- outputs/v8_delivery_category_a_avg60.csv
- outputs/v8_delivery_category_b_each_day60.csv
- outputs/v8_fundamental_ranked_candidates.csv
- outputs/v8_fundamental_report.csv

Important current data limitation from supplied report artifact:
- Delivery cache coverage was only 8 distinct dates, from 2026-10-13 to 2026-10-22.
- data/inputs/fundamental_metrics.csv was empty and fundamental thresholds remained unconfigured.
- Therefore local tests can validate logic, but a live final shortlist cannot be claimed until five-session data and verified fundamental metrics/configuration are available.
- This patch is not deployed to GitHub. Apply it and run GitHub Actions to validate deployment.

Local validation intended:
python -m pytest -q test_delivery_categories.py test_top50_rvol_selection.py test_selection_pipeline_order.py test_liquidity_filter.py test_fundamental_filter.py test_v8_regression.py
