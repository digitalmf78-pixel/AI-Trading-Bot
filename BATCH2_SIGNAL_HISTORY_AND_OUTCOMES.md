# Batch 2 — Signal History and Shadow Outcomes

## Scope and safety
This is an observation-only sidecar. It does not feed data back into the scanner's candidate dataframe, any selection/ranking step, V8 score, gate, Telegram text, or order workflow. The Master Specification and all approved scanner thresholds/formulas remain unchanged.

## Durable signal history (B2-1)
- Per-run copy: `outputs/signal_log.csv`.
- Durable append-only history: `data/signal_history/signal_log.csv`.
- Schema marker: `data/signal_history/schema_version.txt`, currently `1.0`.
- Existing durable rows are never rewritten. The workflow validates the existing key set and all signal-time fields, then appends only new `(EODDate, TckrSymb)` keys.
- Future outcome columns in the durable signal snapshot remain blank. Outcome updates are stored separately so the signal-time snapshot is immutable.
- Outcome sidecar: `data/signal_history/signal_outcomes.csv`, keyed by `(EODDate, TckrSymb, HorizonSessions)`; exact retries are no-ops and conflicting payloads fail closed.
- Workflow commits only these explicit data paths, uses `git add -f`, rebases onto the latest branch head, and pushes to the current workflow branch. The scheduled workflow's push trigger remains restricted to `main` and its workflow-file path, so data commits do not recursively start another scan.
- Bounds: signal history maximum 100,000 rows / 25 MiB; outcome history maximum 300,000 rows / 50 MiB. Exceeding a bound stops persistence for review; old rows are not pruned.
- No secrets, account-specific sizing, or risk-config values are included.

## Shadow cohort and snapshots (B2-2)
- `signal_cohort_assembly.py` and `signal_shadow_store.py` remain independently tested observational helpers.
- The live scanner does **not** invoke the snapshot/stage-event writer. Its append-only JSONL storage has no enforced row/byte ceiling, so it is intentionally skipped until a bounded retention policy is implemented.
- These helpers are not part of scanner selection, ranking, scoring, Telegram output, or the order workflow.

### Outcome definitions
- **Entry reference:** the `OpnPric` (official NSE Bhavcopy Open) of the first official NSE equity session strictly after the signal date, stored as `NEXT_SESSION_OPEN`. This is a research reference price, not an assumed live fill.
- **Result5D / Result10D / Result20D:** raw price return from that next-session Open to the Close of the 5th / 10th / 20th official NSE equity session strictly after the signal date. The entry session itself counts as session 1.
- **MFE / MAE:** stored in the per-run `outputs/signal_log.csv` only when the 20-session horizon is complete. MFE = (maximum High / next-session Open - 1) × 100. MAE = (minimum Low / next-session Open - 1) × 100. The outcome store retains MFE/MAE separately for each 5/10/20-session horizon.
- **Completeness:** every required official session must be present, and the symbol must have valid positive Open, High, Low, and Close values for every session. Missing/duplicate/invalid data means no outcome is written for that horizon; it remains blank and can be evaluated on a later EOD run.
- **Point-in-time:** snapshot fields are built only from the signal-time cohort and stage reports. Forward OHLC is used only in the separate outcome store, never in the original signal snapshot or scanner selection.
- **Fees/slippage:** `NOT_CONFIGURED`. Reported returns are raw price movement only; no net performance is claimed.
- Outcome failures print a warning and do not stop the scanner.

## Experimental scores (B2-3)
- Existing numeric formulas and legacy compatibility columns remain unchanged.
- Additional `ExperimentalAccumulationScore/Status` and `ExperimentalConsolidationScore/Status` columns explicitly mark these values `EXPERIMENTAL_NOT_APPROVED_NOT_BACKTESTED`.
- Code search found no downstream use of the legacy accumulation/consolidation columns outside their own calculations and tests. Telegram construction does not include these fields.
- These scores remain excluded from selection, ranking, and V8 logic.

## Observation wording (B2-4)
- Potential accumulation reason explicitly says `OBSERVATION_ONLY_NOT_MEASURED`.
- Breakout/pullback observation labels explicitly say `OBSERVATION_ONLY_NOT_A_TRADE_ENTRY`; confirmed-entry report remains tied to the existing final EOD gates.
- Track 2 docstring now accurately states that the scanner invokes it as an isolated non-gating observer.

## Verification boundary
The 2026-11-09 baseline artifact and its funnel counts are documented in `BATCH2_READ_ONLY_AUDIT_2026-11-11.md`. A same-input before/after full scanner replay is not claimed until it is actually run. Unit/CI results must be read from the PR's Actions checks; a real EOD persistence run is still required to verify repository writes end-to-end.
