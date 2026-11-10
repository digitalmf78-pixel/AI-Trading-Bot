# NSE V8.0 — Signal Log + Shadow Run Design
**Date:** 10-Nov-2026  
**Repository:** digitalmf78-pixel/AI-Trading-Bot  
**Working branch:** audit/implementation-roadmap-2026-11-10  
**Status:** Design proposal — documentation only; implementation not yet started.

## 1. Safety and scope
- This is an observational sidecar to the existing EOD scanner.
- It must not alter Track 1 or Track 2 eligibility, ranking, Telegram messages, entry gates, stops, targets, sizing, or existing reports.
- The original `Pasted text(20261009-143842).txt` Master Specification remains immutable.
- Shadow calculations must never feed values back into the signal-time decision.
- Missing, stale, ambiguous, or incomplete inputs remain explicitly unavailable; never substitute or fabricate values.
- Only EOD runs create signal snapshots. PREMARKET runs must not create or mutate EOD signal snapshots.
- No secrets, account-specific risk configuration, private credentials, or account-derived position sizing may enter the signal store.

## 2. Proposed storage layout
Use repository-tracked, date-partitioned files so each EOD partition is immutable and auditable:

- `data/signals/snapshots/YYYY-MM-DD.jsonl` — one canonical point-in-time candidate snapshot per signal key.
- `data/signals/stage_events/YYYY-MM-DD.jsonl` — stage transitions and reasons observed for that EOD run.
- `data/signals/outcomes/YYYY-MM-DD.jsonl` — outcome observations appended when 5/10/20-session horizons become complete.
- `data/signals/manifests/YYYY-MM-DD.json` — run metadata, source file hashes, row counts, coverage, schema version, strategy version, and payload hashes.

JSONL is proposed for append-friendly records and preservation of nested evidence. Files are partitioned by EOD date to avoid rewriting historical partitions. Existing CSV reports remain unchanged and continue to be the source inputs for the first implementation.

## 3. Canonical identity and idempotency
- `signal_id`: SHA-256 of the canonical tuple `EODDate | Symbol | StrategyVersion | SignalType`.
- Initial `SignalType`: `EOD_CANDIDATE`; do not invent additional signal classes until mapped to actual existing outputs.
- `StrategyVersion`: exact scanner Git commit SHA, not a manually typed label.
- `snapshot_payload_sha256`: hash of canonicalized signal-time payload, excluding volatile workflow timestamps.
- Exact duplicate key + exact payload hash: idempotent no-op.
- Exact duplicate key + different payload hash: fail closed, preserve the existing record, and emit a conflict diagnostic. Never silently overwrite a prior snapshot.
- A deliberate corrected/reprocessed record requires a separately reviewed revision policy; do not silently change the identity rule during implementation.

## 4. Snapshot record — required fields
Each snapshot record should contain:

### Identity and run provenance
- `schema_version`
- `signal_id`
- `EODDate` (NSE exchange-local date, ISO-8601)
- `Symbol` and available canonical instrument identifiers
- `SignalType`
- `StrategyVersion` (Git SHA)
- `WorkflowRunId`, `WorkflowRunAttempt`, `RunMode`
- `CreatedAtUTC` and `ExchangeTimezone` = `Asia/Kolkata`

### Signal-time decision and stage summary
- Current final status and reason, if present
- Entry zone / proposed entry, stop and target values only when supplied by existing scanner outputs
- Per-stage status and reason for every stage actually represented in the source reports
- Explicit missing-stage marker where an expected report or row is absent; do not infer PASS/REJECT
- Source report names and source row identifiers where available

### Point-in-time evidence
- Price and volume fields, RVOL and its baseline, Delivery A/B evidence, liquidity observations, fundamental values and verification statuses, technical observations, sector/news/event evidence, risk status, and other fields actually available at signal time
- Each evidence item retains its own as-of date/time, source, verification/freshness status, and missing-data status where the source provides them
- Preserve raw source values and statuses; do not replace them with later refreshed values
- Exclude account-specific sizing values and redact any sensitive fields before serialization

### Data quality and assumptions
- Data coverage summary and missing-data flags
- Source file hashes and snapshot payload hash
- Fees/slippage assumption version and values, explicitly marked `NOT_CONFIGURED` until approved
- No assumed fees, slippage, or benchmark values may be presented as measured facts

## 5. Stage event record
One event per observed candidate/stage/status transition, containing:
- `event_id`, `signal_id`, `EODDate`, `Symbol`, `StageName`
- `Status`, `ReasonCode`, `ReasonText`
- `ObservedAtUTC`, `StrategyVersion`, `SourceReport`, `SourceRowHash`
- `PreviousStatus` only when a real prior event exists; never infer a transition from absent data

Stage events are an audit trail, not a new decision engine. Preserve all source statuses including PASS, REJECT, WAIT_FOR_DATA, WATCH, and any module-specific status without coercing unlike statuses into a single meaning.

## 6. Shadow outcome record
One record per `signal_id` and horizon (5, 10, or 20 distinct official NSE trading sessions):
- `signal_id`, `Symbol`, `SignalEODDate`, `HorizonSessions`
- `OutcomeStatus`: `PENDING`, `COMPLETE`, or `WAIT_FOR_DATA`
- `HorizonEndDate`, `EntryReference`, `EntryReferenceType`
- `CloseReturnPct`, `MFE_Pct`, `MAE_Pct`
- `MaxFavorablePrice`, `MaxAdversePrice`, `ObservedSessionCount`
- `PriceSource`, `PriceCoverageStatus`, `OutcomePayloadHash`, `CalculatedAtUTC`

Outcome rules:
- Use only official, distinct NSE equity sessions after the signal EOD date; use the repository's official trading calendar and existing validated Bhavcopy history.
- The signal EOD close is the default reference price for research outcome measurement; label it explicitly as `SIGNAL_EOD_CLOSE`. This is not a claim that a live trade filled at that price.
- MFE/MAE definitions must be fixed in tests before implementation: favorable/adverse excursion are measured from the same reference price over the forward horizon, using forward High/Low respectively.
- Do not calculate a horizon until all required sessions and valid OHLC values are available. Otherwise retain `PENDING` or `WAIT_FOR_DATA`.
- Do not use future observations in snapshot fields, stage decisions, rankings, or signal-time status.
- Fees/slippage-adjusted returns remain unavailable until assumptions are explicitly approved; raw price movement and net performance must never be conflated.

## 7. Run manifest and persistence
Manifest should record:
- EOD date, run mode, Git SHA, workflow run ID/attempt, schema version
- Input report paths, SHA-256 hashes, row counts and coverage summary
- Snapshot/stage/outcome record counts and payload hashes
- Duplicate counts, conflict counts, missing report list, and overall persistence status

Persistence workflow proposal:
1. Run the existing scanner unchanged.
2. If mode is EOD and scanner succeeds, build the signal snapshot from the generated reports.
3. Validate schema, required fields, redaction, key uniqueness, hashes, and point-in-time date constraints.
4. Compare against any existing EOD partition; exact reruns are no-ops, conflicting payloads fail closed.
5. Commit only `data/signals/**` on the working branch, using a dedicated commit message. Do not stage broad paths.
6. Upload the manifest and diagnostics as workflow artifacts even when persistence validation fails, without marking invalid records as persisted.
7. Do not modify the existing Fundamental Cache persistence step or its commit scope.

The current workflow uses a branch-scoped concurrency group and separately commits Fundamental Cache files. The signal persistence step must be designed around that existing commit/rebase behavior and must stage only its own paths to avoid mixing unrelated changes.

## 8. Test plan and exit criteria
Required tests before calling Step 1 complete:
- Schema validation and deterministic canonical serialization
- Stable signal IDs across retries and different runner timestamps
- Exact duplicate run is a no-op
- Same key with changed payload is a conflict and does not overwrite
- EOD-only behavior; PREMARKET creates no EOD signal rows
- All candidates in the defined input cohort are represented, including WAIT/REJECT statuses where present in source data
- Missing report/row remains explicit and never becomes PASS
- Point-in-time isolation: no record field can use data dated after EODDate
- Official-calendar session counting, holidays, special sessions and missing sessions
- 5/10/20 outcome pending/completion transitions
- MFE/MAE calculations on deterministic synthetic OHLC fixtures
- No secret/account-derived fields in persisted JSONL or manifests
- Workflow stages only `data/signals/**`, preserves Fundamental Cache commits, and uploads diagnostics
- Existing scanner outputs and selection counts are byte-for-byte or semantically unchanged in a shadow-enabled test run

Step 1 is complete only after append-only daily history is persisted, outcomes are reproducible, all tests pass, and a real EOD shadow run is audited. No production gate changes are included.

## 9. Open implementation questions (must be resolved by code mapping/tests, not guesses)
1. Exact candidate cohort: determine which existing report is the canonical full cohort and how to include every Mainboard candidate without misrepresenting candidates omitted from downstream reports.
2. Canonical symbol identity: inspect existing NSE symbol/series mapping and handle symbol changes without merging unrelated instruments.
3. Entry reference: signal EOD close is proposed for research measurement; confirm whether existing approved strategy requires a different reference for each setup.
4. Fee/slippage assumptions: currently unapproved; store as `NOT_CONFIGURED` until decided.
5. Revision policy: changed data for an already-persisted EOD + strategy key must conflict rather than overwrite until a reviewed revision model is approved.
6. Workflow write permissions and branch protection: verify actual branch behavior before enabling repository writes for the shadow store.

---
**Change control:** This file is a design proposal only. No scanner code, production workflow, Master Specification, selection threshold, ranking, Telegram output, or main-branch content is changed by this document.
