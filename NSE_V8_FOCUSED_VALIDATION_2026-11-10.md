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
- Added four new cohort tests. Current source contains 31 cohort test functions and 18 shadow-store test functions (49 total).
- Added the working audit branch to the CI workflow's push branch allow-list. This workflow-file change is confined to the working branch; main remains untouched.
- A status lookup for the workflow-triggering commit returned no status checks yet. Therefore the latest 44-test revision and full repository CI are **not yet confirmed executed**. The previously reported 34-pass result remains limited to the earlier revision only.

- Added one further test for reserved internal join-key columns in an empty evidence report. Current inventory is now 29 cohort + 16 shadow-store test functions (45 total).
- A new Python test-file commit was pushed after the audit-branch CI trigger was added, but the GitHub connector's commit-status endpoint still returns no checks, and its workflow-run helper only exposes pull-request-triggered runs. Actual workflow execution therefore remains unverified; do not interpret an empty status list as a pass.

- Added empty-stage-report schema checks: duplicate columns and reserved internal join keys now fail closed even when the DataFrame has zero rows. Added two tests for these cases.
- Current test inventory is 31 cohort + 16 shadow-store test functions (47 total).
- The latest pushed commit has no status checks and no workflow run visible through the connected GitHub actions read methods. The available workflow-run helper is limited to pull-request-triggered runs; no workflow-dispatch/write action is exposed. Consequently CI execution is still pending/unverified.


## Shadow-store schema hardening (2026-11-10)
- Append-time and existing-file validation now enforce exact top-level schemas for snapshot records and stage-event records. Recomputing a valid digest no longer permits extra arbitrary fields to be persisted.
- Snapshot signal_fields are rechecked against the approved field allow-list at append/read validation, and source_reports must be a list of strings.
- Sensitive-key rejection is repeated for persisted records, not only at builder time.
- Non-mapping records fail closed with a domain validation error.
- Added three shadow-store test functions (one parameterized), bringing the current inventory to 31 Cohort Assembly + 18 Signal Shadow Store test functions = 49 functions. Pytest-expanded case count is 50 because the non-mapping test has two parameters.
- These latest changes have not been executed in a Python test environment. Prior 34-pass result remains for an earlier revision only; full CI remains unverified.


## Additional input-type validation (2026-11-10)
- Moved record mapping validation ahead of key membership checks so malformed list/string records fail with the intended validation error.
- Snapshot builder now rejects a plain string/bytes for source_reports rather than treating it as an iterable of individual characters.
- Snapshot field names must be strings before allow-list sorting; persisted snapshots recheck this condition.
- Added two tests covering string source_reports and non-string field keys. Latest inventory: 31 Cohort Assembly + 18 Signal Shadow Store test functions = 49 functions; pytest-expanded cases = 50.
- No tests have been executed against this latest revision. GitHub connector exposes no run for the push commit; empty status response is not a pass.


## Focused local execution result (2026-11-10)
- Retrieved the four current branch files from `audit/implementation-roadmap-2026-11-10` and ran the two focused test modules in an isolated local Python environment (Python 3.13.5, pandas 2.2.3, pytest 9.0.2).
- Initial combined run exposed a real defect: a stage report payload field named `CoverageStatus` could alias the generated `<Stage>__CoverageStatus` column without raising. The implementation now rejects both reserved payload names `CoverageStatus` and `CoverageReason`; the test covers both names.
- After the branch fix, combined focused result: **54 passed in 0.27s**.
- Syntax compilation check: **4/4 files passed** (`signal_cohort_assembly.py`, `signal_shadow_store.py`, and their two focused test files).
- This is a local focused test run of the current branch modules/tests, not a GitHub Actions CI run. Full repository CI, broader regression suite, and real EOD shadow validation remain unverified.
- The change remains on the audit branch only. No production scanner wiring, trading filter, Telegram behavior, Master Specification, or main-branch code was changed.

## Follow-up hardening after the 54-case local run (2026-11-10)
The following changes were committed after the 54-case focused execution. THEY HAVE NOT YET BEEN EXECUTED, so the earlier 54-pass result does not cover them.

### Signal Shadow Store
- Enforce key_field / hash_field pairing: snapshots must use signal_id + snapshot_payload_sha256; stage events must use event_id + event_id.
- Revalidate snapshot identity by recomputing signal_id from canonical EOD date, uppercase symbol, strategy Git SHA, and signal type.
- Revalidate snapshot schema version, signal type, EOD run mode, exchange timezone, date representation, and timestamp metadata at append time.
- Require StrategyVersion to be a 40-character Git commit SHA.
- Require CreatedAtUTC and ObservedAtUTC values to be UTC (not merely any timezone-aware timestamp).
- Added seven focused tests across key/hash mismatch, recomputed-but-invalid identity, reserved metadata, invalid strategy SHA, and UTC timestamp rules.

### Cohort Assembly
- Reject non-scalar symbol and series identity values explicitly rather than allowing pandas isna() array ambiguity.
- Added empty-Mainboard-cohort coverage and tests for non-scalar symbol/series values in Mainboard and News evidence.
- Added four new test functions (one parameterized with two cases).

### Current validation state
- Current focused test inventory is approximately 66 pytest cases (including parameterized cases); this count is derived from the known test additions and has NOT been confirmed by executing pytest.
- No new local test execution is available for these post-54-case changes in this session. Do not label them passed.
- Latest branch commit: 8dfe613f8229adba03a75195f370dd1e83b4f171.
- Latest GitHub combined-status lookup returned an empty status list, and the available workflow-run lookup returned no runs. GitHub Actions execution is therefore still unverified.
- Branch comparison now reports 68 commits ahead and 1 behind main. Main has advanced independently; no merge/rebase was attempted and main remains untouched by this work.
- Production scanner integration, trading filters, workflow persistence, Telegram behavior, and the Master Specification remain unchanged.
