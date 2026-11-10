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
