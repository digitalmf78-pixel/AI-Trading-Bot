# NSE V8.0 — Integrated Audit Correction + XBRL Statement Reconciliation

दिनांक: 03-Nov-2026

## Target baseline

- Latest supplied GitHub Actions run checked out `98c834458d61f5321c02844b9faf652ff1381f44`, then its cache-persistence step pushed `e18dda8` to `main` (the run log shows `98c8344..e18dda8 HEAD -> main`).
- The patch is assembled against the uploaded source ZIP corresponding to the checked-out code snapshot; it excludes the Fundamental CSV/cache files changed by the workflow commit. The ZIP has no `.git` directory, so exact byte-for-byte equivalence of every archived file cannot be independently proven.
- The exposed source files at `e18dda8` retain the same scanner/fundamental-shortlist structure as the uploaded snapshot. Before applying, verify that `main` has not received further code changes; do not overwrite newer changes.

## What this integrated patch changes

### 1. Fundamental calculation-basis fail-closed assessment

`fundamental_shortlist.py` only treats these explicit bases as assessable:
- `QUARTERLY_TTM_ALIGNED_STATEMENTS`
- `ANNUAL_ALIGNED_STATEMENTS`

Blank, legacy/unknown, unaligned, or unsupported bases return `WAIT_FOR_DATA`. Existing stored metric values and dated cache snapshots are not rewritten.

### 2. Fundamental data is not a stock-rejection gate at the collection stage

`volume_gainer.py` retains every Delivery Category-A candidate (Category B is a subset of A) for downstream liquidity/technical evaluation regardless of Fundamental PASS/FAIL/WAIT_FOR_DATA. Fundamental fields and score remain attached for reporting/ranking. If fundamental collection/assessment errors, Category-A rows are retained with explicit `WAIT_FOR_DATA` metadata.

This implements the latest project instruction: collect/assess fundamentals for all Delivery A/B candidates, but do not drop a candidate merely because fundamentals are missing or unverified at this stage.

### 3. Remove obsolete Top-50 test expectation

`test_top50_rvol_selection.py` is replaced with tests for the current uncapped strict `RVOL > 1.5` selector. It checks that all qualifying candidates are retained, while `RVOL == 1.5`, below-threshold, missing, and WAIT_FOR_DATA rows do not qualify.

### 4. Run XBRL candidate extraction and statement reconciliation in CI

Adds:
- `nse_xbrl_financial_fact_audit.py`
- `test_nse_xbrl_financial_fact_audit.py`
- `nse_xbrl_statement_reconciliation.py`
- `test_nse_xbrl_statement_reconciliation.py`

The scheduled workflow now runs both audit-only scripts after the existing official NSE XBRL sample download. Their outputs are included in the report artifact.

The XBRL scripts are read-only with respect to trading inputs: they do not modify `fundamental_metrics.csv`, calculate TTM, select a canonical accounting tag, or promote any fact to `VERIFIED`.

## Actual-sample validation performed locally

Using the five XML files and diagnostic JSON from uploaded NSE report artifact run `41610810465` (not the later logs-only run `41615959672`):

- XML files audited: 5/5
- Filing symbol identity: 5/5 MATCH
- Candidate numeric facts extracted by fact audit: 97
- Statement arithmetic checks: 55
- Arithmetic checks within XBRL rounding tolerance: 55
- Arithmetic mismatches: 0
- DNAMEDIA dimensioned net-profit conflicts retained as anomalies: 2
- Q4 operating cash-flow facts: not present in these five samples
- All facts remain candidate-only / not verified

Important: 55/55 arithmetic checks passing supports internal arithmetic consistency only. It does not establish taxonomy correctness, audited filing completeness, point-in-time publication eligibility, or provider reconciliation. The two DNAMEDIA net-profit anomalies remain unresolved; no preferred value is selected.

## Validation performed

- Targeted Fundamental/RVOL/pipeline/XBRL tests: 39 passed.
- Workflow Fundamental/Delivery/Pipeline test batch: 88 passed.
- Workflow XBRL/P2 test batch: 54 passed.
- V8 regression script: 27 passed.
- Sector/news/cache unittest batch: 39 passed.
- News parser tests: 4 passed.
- Corporate event tests: 5 passed.
- RSI retest tests: 5 passed.
- Python `compileall`: all 56 Python files passed.
- GitHub Actions YAML parsed successfully; 15 workflow steps found.

The test batches overlap (for example, provider and shortlist tests appear in more than one batch); do not add the batch counts and call the sum a unique test count. A single full `pytest -q` run timed out in this environment, so the completed targeted/workflow batches are the validation evidence.

## Not changed

- Master Specification
- Mainboard universe rules
- RVOL threshold `> 1.5` and prior 20-full-session baseline
- Delivery Category A five-session average `>= 60%`
- Delivery Category B each of five sessions `>= 60%`
- Liquidity threshold or formula
- Technical entry/exit calculations
- Existing TTM arithmetic
- Fundamental cache values and historical snapshots
- XBRL verification statuses

## Apply safely

1. Confirm GitHub `main` still contains the target baseline or rebase these file changes onto the latest `main`.
2. Review the diff for the 12 patch files.
3. Apply the patch and run the scheduled workflow manually in EOD mode.
4. Download the new `nse-v8-reports` artifact and inspect both XBRL audit folders.
5. Do not mark any XBRL fact verified based only on arithmetic checks.

No GitHub push, merge, or deployment was performed by this local patch preparation.
