# NSE V8 Observational Store and Cohort Focused Validation — 2026-11-10

## Scope
Focused validation only for the observational modules:
- `signal_cohort_assembly.py` and `test_signal_cohort_assembly.py`
- `signal_shadow_store.py` and `test_signal_shadow_store.py`

No scanner integration, production filter changes, workflow behavior changes, PR creation, or merge.

## Execution method and limitation
The repository could not be cloned into the local runtime because outbound DNS/network access to github.com was unavailable. The latest branch source and test contents were fetched through the connected GitHub repository integration and reproduced in an isolated local test directory with the available Python environment (Python 3.13.5, pandas 2.2.3, pytest 9.0.2). Therefore this is a focused isolated validation of the fetched branch logic and test cases, not a full repository checkout or a GitHub Actions CI run. Full-repository CI remains outstanding.

## Results
Commands executed:
- `python -m py_compile signal_cohort_assembly.py test_signal_cohort_assembly.py`
- `python -m py_compile signal_shadow_store.py test_signal_shadow_store.py`
- `python -m pytest -q test_signal_cohort_assembly.py test_signal_shadow_store.py`

Result: **34 passed in 0.28s**.
- Cohort Assembly: 18 tests
- Signal Shadow Store: 16 tests

## Finding and correction
An initial strict rule requiring `SctySrs` on both sides of every symbol join caused an existing cohort test to fail because the Delivery report legitimately supplies a symbol key without a series column. The contract was refined:
- If both sides provide `SctySrs`, mismatches fail closed.
- If one side omits `SctySrs`, the symbol join remains usable (symbol uniqueness is already enforced), but diagnostics explicitly record that series alignment was not checked.
- One-to-many News/Corporate Event evidence follows the same rule; actual supplied series mismatches still fail closed.

After this correction, all 34 focused tests passed in the isolated harness.

## Remaining work
1. Run the full repository GitHub Actions CI on a PR or an explicitly authorized workflow trigger.
2. Review the complete repository test suite for integration interactions.
3. Keep both observational modules unwired until full validation and explicit production-integration approval.
4. Keep main branch unchanged; continue work only on `audit/implementation-roadmap-2026-11-10`.


## Subsequent hardening after the 34-test run
After the isolated 34-test execution above, additional cohort validation was added:
- Optional series metadata absence is now recorded as a diagnostic rather than universally rejecting otherwise unique symbol joins; supplied series mismatches still fail closed.
- Reserved internal columns, generated cohort fields, generated stage payload/coverage fields, and one-to-many evidence coverage fields are protected against silent overwrites.
- Duplicate evidence columns are rejected.
- New cohort tests were added for these cases. **These newly added tests have not yet been executed**, so the previously reported 34-pass result applies only to the exact source revision tested before these subsequent additions. The current test files contain 24 cohort test functions and 16 shadow-store test functions (40 total); current full focused re-run is pending.


## Latest follow-up review (2026-11-10)
- Fixed a malformed f-string in the one-to-many evidence series-mismatch diagnostic before attempting the next test run.
- Added fail-closed guards for generated coverage columns when stage reports are missing or empty.
- Added validation for duplicate columns and reserved coverage columns in empty News/Event evidence frames.
- Added four new cohort tests. Current source contains 29 cohort test functions and 16 shadow-store test functions (45 total).
- Added the working audit branch to the CI workflow's push branch allow-list. This workflow-file change is confined to the working branch; main remains untouched.
- A status lookup for the workflow-triggering commit returned no status checks yet. Therefore the latest 44-test revision and full repository CI are **not yet confirmed executed**. The previously reported 34-pass result remains limited to the earlier revision only.

- Added one further test for reserved internal join-key columns in an empty evidence report. Current inventory is now 29 cohort + 16 shadow-store test functions (45 total).
- A new Python test-file commit was pushed after the audit-branch CI trigger was added, but the GitHub connector's commit-status endpoint still returns no checks, and its workflow-run helper only exposes pull-request-triggered runs. Actual workflow execution therefore remains unverified; do not interpret an empty status list as a pass.
