NSE V8.0 — DELIVERY-FIRST STOCK SELECTION FIX
Date: 2026-10-20

PURPOSE
Change only the stock-selection order and the five-session Delivery rule in the MAIN NSE Swing Trading V8.0 project. Other technical, sector, news, 3+1, risk/reward, and final-watchlist conditions remain unchanged.

NEW SELECTION ORDER
1. Start with the valid current EOD equity universe.
2. FIRST apply the Delivery filter using the latest 5 distinct valid trading sessions.
3. A stock passes only when each of those 5 sessions individually has Delivery % >= 60.00%.
4. Exactly 60.00% passes. If even one day is below 60.00%, reject the stock.
5. If five valid sessions or the required per-symbol values are missing, mark WAIT_FOR_DATA and do not pass the stock.
6. Only Delivery-qualified stocks continue into the existing 5-day / prior-20-session volume-history checks.
7. Calculate RVOL and select Top 20 from the remaining qualified stocks.
8. Keep all existing later technical, sector, news, mandatory 3+1, risk/reward and final-watchlist conditions as they are.

AvgDelivery5D remains in reports for information/scoring only; it is NOT the pass/fail gate.

FILES TO REPLACE IN THE MAIN REPOSITORY
- delivery_filter.py
- volume_gainer.py
- v8_layers_14_41.py (docstring only; calculation/conditions unchanged)
- test_v8_regression.py (regression tests updated for the new rule/order)

DO NOT replace or edit .github/workflows/delivery_60_valuation_watchlist.yml or the separate delivery-watchlist test project for this change.

LOCAL VALIDATION
- Python compilation passed for the changed Python files.
- `python test_v8_regression.py`: all 26 V8 regression tests passed.
- Full pytest collection was not used because the repository contains `delivery_60_valuation_watchlist_inline_test.py`, which executes workflow code and raises SystemExit during collection; it also attempted network calls in this offline environment. This is not a failure of the 26 V8 regression tests.

GITHUB STEPS
1. Open the MAIN `digitalmf78-pixel/AI-Trading-Bot` repository.
2. Replace each listed file with the same-named file from this patch, keeping the file at repository root.
3. Commit the changes.
4. Run the existing NSE V8 workflow.
5. Check `v8_delivery_first_audit.csv`: passing rows must have DeliveryDailyPassCount=5 and MinDelivery5D >= 60.00.
6. Check `v8_primary_shortlist_top20.csv`: it should contain up to 20 stocks selected only after the daily Delivery gate and existing volume-history/RVOL ranking.
7. Inspect the fresh report before considering the project validated. No GitHub changes have been made by this patch creation.
