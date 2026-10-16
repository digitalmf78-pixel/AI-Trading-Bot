# NSE V8 — Sector Mapping Cache Reconciliation Fix

## Finding from `nse-v8-reports-38878011010.zip`

The fresh audit `data/reports/sector_candidate_mapping_20261015.csv` marks `SPENCERS` and `MODINATUR` as `WAIT_FOR_DATA`, but the persistent `data/inputs/sector_map.csv` still contains older sector assignments for both symbols. The EOD watchlist then consumes those cached rows and reports sector-strength `PASS`, which contradicts the fresh mapping audit.

This patch changes `sector_data.py` so that, after the current candidate audit is generated, stale cached mappings are removed for candidates whose current status is `WAIT_FOR_DATA`, `ETF_UNDERLYING_INDEX_UNSUPPORTED`, or `ETF_UNDERLYING_INDEX_REQUIRED`. A mapping supplied by the current official refresh is preserved. Cache rows for unrelated, non-candidate symbols remain intact. No sector is guessed.

## Files

- `sector_data.py` — complete replacement file based on the version with the Nifty Indices session bootstrap/history fallback.
- `test_sector_mapping_cache_reconciliation.py` — focused regression tests.
- `.github/workflows/sector-mapping-cache-reconciliation.yml` — standalone compile + regression test workflow.

## Apply in GitHub

1. Replace the repository's entire `sector_data.py` with the file in this ZIP.
2. Add `test_sector_mapping_cache_reconciliation.py` to the repository root.
3. Add `.github/workflows/sector-mapping-cache-reconciliation.yml` at that exact path.
4. Commit the changes and run the new **Sector Mapping Cache Reconciliation** workflow.
5. Run the normal NSE V8 workflow afterward and upload its report ZIP.

## Local verification performed

- Python compile: PASS
- Cache reconciliation tests: 3/3 PASS
- Existing ETF mapping tests: 2/2 PASS
- Existing Nifty Indices history/bootstrap tests: 4/4 PASS
- Total tests run here: 9/9 PASS

This is a local test result only. It does not mean GitHub Actions has passed yet. The EOD report must be rerun to confirm that unresolved candidates no longer receive sector-strength values from stale cache entries. The patch does not change Delivery Filter or Mandatory 3+1 confirmation rules.
