NSE V8 Phase 2 checkpoint — 2026-10-21 (new log reviewed)

Latest run checkout commit: 60a54c5481893b72f98b12911109bf8e71d06069
Workflow: .github/workflows/nse-test-scheduled.yml
Test failure: test_liquidity_filter.py::test_pipeline_order_delivery_then_rvol_top20_then_liquidity
Result in focused test group: 24 passed, 1 failed.
Failure: test expects the obsolete label "STEP 6B: LIQUIDITY FILTER — AFTER RVOL TOP 20"; current agreed architecture places Liquidity before Fundamental and before RVOL.

Action: include a replacement test_liquidity_filter.py enforcing Delivery -> Liquidity -> Fundamental -> RVOL Top 20 -> Technical.
Do not interpret this failed run as proof the Phase 2 patch is deployed. Patch remains not deployed.
