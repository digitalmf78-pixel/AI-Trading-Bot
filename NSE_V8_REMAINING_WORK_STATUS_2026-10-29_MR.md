# NSE V8 — Remaining Work Status (29 Oct 2026)

## Source inspected
- Inspected the uploaded `AI-Trading-Bot-main (1).zip` against the 28 Oct handover and log archive.
- The repository snapshot already contains the targeted official-filing lookup diagnostics code and its tests. Do not re-apply that patch blindly. This only confirms the uploaded ZIP contents; it does not prove what is currently deployed on GitHub.

## Change made in this working copy
The `nse-test-scheduled.yml` Actions cache did not include either:
- `data/inputs/fundamental_metrics.csv`
- `outputs/v8_official_financial_results_filings.csv`

Both are now included in the existing Actions cache paths, so the existing restore-key chain can reuse these files between workflow runs. Added `test_fundamental_cache_persistence_workflow.py` to guard this configuration.

**Important:** This is GitHub Actions cache persistence in the repository workspace, not a Git commit of changing CSV data to the repository history. No workflow write permissions or automatic commit step was added.

## Validation run
Focused tests:
`pytest -q test_fundamental_cache_persistence_workflow.py test_fundamental_official_filings.py test_selection_pipeline_order.py test_fundamental_data_provider.py`

Result: **30 passed**.

The complete test suite was not completed in this environment; an initial full-suite attempt was interrupted after the environment's 60-second execution limit. No claim is made that all tests pass.

## Observations requiring further diagnosis
1. The 28 Oct log says the core technical screen passed 0 of 14 candidates, while 14 candidates continued through later layers. The current code annotates `CandidateScreenStatus` and returns the full frame, so technical rejects are not removed at this point. Some comments elsewhere describe filtering before expensive news/sector processing, so this behavior/comment mismatch needs to be reconciled against the master specification and report artifacts before changing it.
2. Sector history was unavailable for the exact EOD date; sector scores must remain `WAIT_FOR_DATA` unless supported by data.
3. Risk configuration values are null/unverified. Do not invent values or enable position sizing/BUY decisions.
4. The 18 official filing pairs must remain unverified unless exact symbol + exact financial period-end + valid publication date by the EOD cutoff are evidenced. No period substitution is allowed.

## Not done
- No live NSE filing verification was claimed.
- No GitHub push or remote workflow run was performed.
- No stock selection thresholds, RVOL, Delivery, liquidity, technical, or risk rules were relaxed.
- Master specification was not changed.
