NSE V8 Phase 2 — targeted test correction (2026-10-21)

WHY THIS PATCH EXISTS
The latest uploaded GitHub Actions log (run artifact nse-v8-reports-39595178089) checked out commit:
60a54c5481893b72f98b12911109bf8e71d06069

The workflow stopped in the Delivery/Liquidity/Fundamental/Pipeline test group:
24 passed, 1 failed. The failing test was test_pipeline_order_delivery_then_rvol_top20_then_liquidity in test_liquidity_filter.py.
That test still asserted the OLD order (RVOL Top 20 before Liquidity), contradicting the approved target order.

THIS PATCH
Includes a replacement test_liquidity_filter.py that asserts:
Delivery -> Liquidity -> Fundamental -> RVOL ranking/Top 20 -> technical checks.
It also includes the previously prepared Phase 2 replacement files and input templates.

IMPORTANT LIMITATIONS
- This is a patch ZIP only. It has NOT been pushed or deployed to GitHub.
- The uploaded run failed; it is not a successful validation run.
- The uploaded repository ZIP does not fully match the current Actions checkout, so apply against the current main branch and review the diff.
- Fundamental thresholds and risk configuration remain intentionally unset; absent verified values must remain WAIT_FOR_DATA.
- After replacing files and committing, rerun nse-test-scheduled.yml and upload the new logs.
