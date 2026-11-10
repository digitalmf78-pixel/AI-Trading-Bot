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

## Full GitHub Actions regression result (2026-11-10, latest revision)
- Latest audit-branch commit under validation: `540e0cb38e1279a31ed83f2b0eaacc1db83e82ca`.
- GitHub Actions run: [42798190518](https://github.com/digitalmf78-pixel/AI-Trading-Bot/actions/runs/42798190518) — **SUCCESS**.
- Python compile step: **PASS** for all configured scanner and audit modules.
- Unit/data-audit pytest step: **388 passed in 6.81s**.
- V8 regression script: completed successfully (workflow proceeded to the following test step).
- Sector, news, and official-index unittest step: **43 tests passed**.
- The run initially failed on the preceding revision with two test-only compatibility assertions:
  1. The timestamp validator returned a generic UTC error for a naive timestamp; validation now distinguishes missing timezone from a non-UTC offset.
  2. An empty-column dtype assertion assumed pandas object dtype; it now checks the invariant that the coverage column is present and empty, independent of pandas dtype backend.
- The corrected revision's complete workflow is green. This supersedes the earlier 54-case focused-only state and the interim failed run.
- This validates the configured GitHub Actions suite on the audit branch. It does not constitute live NSE EOD data validation or authorize production scanner integration.
- Branch comparison at report update: **71 commits ahead, 1 behind main**. No merge/rebase was attempted; main remains untouched.
- Observational cohort and shadow-store modules remain unwired from the production scanner. Master Specification and trading filters remain unchanged.

## Integration-readiness static audit (2026-11-10)
### Confirmed current production sequence
- `volume_gainer.py` confirms official Mainboard classification before Delivery.
- The scanner fetches all available distinct Delivery reports in the 30-calendar-day window (`required_sessions=5`, `collect_all=True`); A and B are independently calculated, then the full A OR B union is deduplicated before RVOL.
- RVOL is calculated only for the A/B union. The Liquidity stage receives all A/B rows; its configured minimum remains ₹1.5 crore average daily traded value over 20 prior sessions.
- Fundamentals are collected only after Liquidity for every liquidity-qualified row; collection/verification errors are recorded without dropping the liquidity-qualified candidates. The master parameter register's old unresolved item #3 was stale; it has now been marked RESOLVED in line with the explicit 06-Nov-2026 decision.
- No Top-20/Top-50 RVOL cap was found in the current candidate annotation function; its legacy function name `select_top20_analysis_candidates` is misleading, but it returns the complete input frame and assigns ranks without truncation.
### Confirmed gaps / not yet production-ready
1. **Full-Mainboard Track 2 Accumulation:** Delivery Quantity observations are produced from the full Mainboard Delivery audit, but the Potential Accumulation price-response engine, VCP observations and early hybrid watchlists are called with the 758-row A/B union. The separate full-Mainboard SIDEWAYS_ACCUMULATION / DIP_ACCUMULATION research cohort remains unimplemented. It must be a separate Track 2 output and must not alter Track 1 A/B eligibility.
2. **News window:** `news_catalyst.py` explicitly logs and applies a five-calendar-day news window. The data-contract requirement is seven calendar days. This is a real specification-to-code gap; no window change was made during this audit.
3. **Corporate-event horizon:** the issuer announcement API searches a 90-day announcement lookback and records every explicit future event date. The current event report does not restrict confirmed events to the next 20 calendar days. Discovery lookback and display horizon need separate treatment; no event date or horizon was rewritten here.
4. **Stock-specific institutional evidence:** current FII/FPI and DII module is market-wide aggregate only. No stock-specific bulk/block deals, shareholding, pledge, insider/PIT/SAST evidence producer was found in the audited paths. Do not infer stock-level buying from market-wide flows.
5. **Shadow-store deployment:** cohort assembly and append-only signal-store modules remain standalone observational helpers. They are not called from `volume_gainer.py` or the scheduled EOD workflow. No daily `data/signals/**` persistence, run manifest, forward outcome tracker, or real EOD shadow run has been implemented/validated.
6. **Cohort assembly contract:** the canonical base is the full 2,588-row `v8_delivery_dual_category_audit.csv` (not the 758-row A/B union). Stage reports are left-joined and absent rows remain NOT_EVALUATED; News and Events remain separate one-to-many evidence tables. `CohortEligibilityStatus=PASS_MAIN_BOARD_INPUT` is a caller assertion, not an independently verified board classification. `DownstreamReportsPresent/Expected` counts one-to-one stage report coverage only; it excludes News/Event evidence coverage.
7. **Evidence-series join defect fixed:** the News/Event series-alignment code previously indexed the Mainboard series map for every evidence row, including out-of-cohort symbols, which could raise KeyError when an out-of-cohort evidence row carried SctySrs. It now compares only matching cohort symbols, and a regression test preserves the out-of-cohort row as OUT_OF_COHORT.
### Documentation consistency
- The hybrid parameter register's pending list incorrectly still labelled the Fundamentals collection boundary unresolved even though section 18 and README state that Liquidity-first was confirmed on 06-Nov-2026. Item #3 is now marked RESOLVED; no strategy behavior changed.
- Historical audit notes that predate later implementation sections are retained as historical records; later dated sections and the current README/register define the current status.
### Latest regression evidence
- Latest workflow run: [42798705327](https://github.com/digitalmf78-pixel/AI-Trading-Bot/actions/runs/42798705327) — **SUCCESS** on code/test commit `e883d18d89ff9fcd45531d0ce18e644ebc7e2684`.
- Python compile: PASS.
- Configured pytest suite: **389 passed in 6.44s**.
- V8 regression script: PASS (workflow continued).
- Sector/news/official-index unittest suite: **43 tests passed**.
- The subsequent documentation-only register correction is on the same audit branch; no production code or Master Specification changed.
- Current branch comparison: **75 commits ahead, 2 behind main**. Main has advanced independently; no merge/rebase was attempted.
- No live EOD run, real NSE fetch validation, Track 2 implementation, or signal-shadow persistence was performed in this audit.

### Additional shadow-store security review
- The design requires redaction of secrets and account-derived values before serialization. Snapshot fields are allow-listed, and the store rejects sensitive-looking **field names**; however, the current stage-event `ReasonText` and `SourceReport` are free-text values and the validator does not inspect string contents for embedded credentials, URLs with secret query parameters, or account-derived values.
- This is not evidence of an existing leak because the helper is not wired into the workflow and the design requires curated/redacted inputs. It is a pre-integration requirement: add explicit safe-text/redaction validation or prove the caller-side redaction contract with tests before enabling persistence.
- No code change was made for this item because a safe redaction policy for free-text reasons has not yet been specified.


## Track 2 Full Mainboard standalone builder — implementation checkpoint (10-Nov-2026)
- Added `track2_full_mainboard.py`: a standalone, non-gating report builder that accepts the official Mainboard-filtered cohort before Delivery A/B, runs Delivery Quantity, Potential Accumulation and VCP observers on the complete unique Mainboard input, and writes all artifacts under `outputs/track2_full_mainboard/`.
- Added optional `output_path` parameters to the three existing observation modules so Track 2 can write isolated artifacts without overwriting Track 1's existing output files. Default paths and existing scanner call sites remain unchanged.
- Added `test_track2_full_mainboard.py` and included it in CI compilation/pytest commands.
- Tests cover full-cohort scope (including A/B-failed and WAIT names), duplicate identity fail-closed behaviour, board-status validation, invalid symbols, observer failure isolation, empty input and category-request validation.
- SIDEWAYS_ACCUMULATION / DIP_ACCUMULATION remain `NOT_CLASSIFIED_PENDING_APPROVED_RULES`; no numeric classification thresholds were added.
- GitHub Actions run [42800483179](https://github.com/digitalmf78-pixel/AI-Trading-Bot/actions/runs/42800483179) — **SUCCESS** on commit `8400ac0f6bfa2b9578ae9ca22bef3e96d7548ce9`: Python compilation PASS; **397 pytest tests passed in 4.02s**; all 33 V8 regression tests PASS; 43 sector/news/official-index unittests PASS.
- The first explicit Track 2 test run exposed a duplicate-key join validation bug. The implementation was corrected to exclude ambiguous identities from observer input while retaining one WAIT_FOR_DATA row in the cohort report; the final run above validates the correction.
- **Not done:** no Track 2 scheduled workflow wiring, no scanner call-site integration, no live EOD run, no real NSE fetch, no Track 1 output or eligibility changes, and no Master Specification change. This remains isolated code on the audit branch.
- Current branch comparison: **90 commits ahead, 2 behind main**. No merge/rebase/PR was performed; main remains untouched.

## Track 2 full-Mainboard validation update (10-Nov-2026)
- Added a synthetic 2,588-symbol Track 2 cohort test and committed it as `5d3db64c4b643b80122d089c60da0972d25bf3a4`.
- Latest GitHub Actions run `42801601368`: **SUCCESS**; configured pytest **398 passed in 7.52s**; V8 regression **33 PASS**; sector/news/official-index **43 PASS**; Python compilation PASS.
- Inspected the actual 09-Nov EOD report artifact `nse-v8-reports-42634890331` read-only. It confirms 2,588 Mainboard symbols (2,385 EQ + 203 BE), with Delivery Quantity already covering all 2,588 (2,253 complete, 335 WAIT).
- Existing Potential Accumulation and VCP outputs remain limited to the 758-row A/B union; 1,830 Mainboard symbols have no evaluation row in those existing reports.
- The artifact does not include raw 200-session Bhavcopy or raw Delivery cache files. The real-data Track 2 observer run is therefore still pending cache restoration. No live NSE fetch was performed.
- Track 2 remains standalone and unwired; no production scanner, main branch, Master Specification, or Track 1 behavior changed.
