# ECMS workflow contract — current EOD and morning phases

## Workflow A — ECMS EOD
- Workflow file: `.github/workflows/ecms-volume-gainers-shadow.yml`.
- Triggers: manual `workflow_dispatch` with mode `eod`, plus weekday schedule at 16:45 IST.
- Scope: only eligible NSE Volume Gainers page rows from that run; never the full Main Board universe or V8 candidate list.
- Restore shared NSE cache read-only using the ordered cache path list; write ECMS state only beneath `data/cache/ecms/` and reports only beneath `outputs/ecms/`.
- Assess every eligible current-page candidate. A candidate must receive exactly one assessment row; missing or failed provider data remains `WAIT_FOR_DATA`.
- Collect free-source fundamental evidence with per-metric provenance and reporting periods. No paid API, mandatory AI provider or secret API key.
- Run strict fundamental shortlist and independent ECMS research scoring separately. Only strict `PASS` plus research `STRONG` and coverage >=80% enters the strong-fundamental hand-off.
- Run official XBRL verification separately and fail closed. Third-party provider data is never described as official verification.
- Attach candidate-specific catalysts and negative-risk evidence; provider/source unavailability is not evidence of no news.
- Upload an EOD-specific artifact bundle and send a separate EOD Telegram message.

## Workflow B — ECMS morning reassessment
- Workflow file: same ECMS workflow, independent `morning` job.
- Triggers: manual `workflow_dispatch` with mode `morning`, plus weekday schedule at 09:20 IST.
- Restore the previous EOD candidate snapshot and ECMS fundamental workspace.
- Assess every eligible current morning-page candidate with the same fundamental framework, including repeated and new entries.
- Preserve EOD results and label morning-only, EOD-only and double-confirmed outcomes separately. Double confirmation requires strict PASS plus research STRONG at both checkpoints.
- Upload a morning-specific artifact bundle and send a separate morning Telegram message.

## CI validation
- Push and pull-request validation compiles ECMS modules and runs the focused ECMS tests, including the Debt/Equity XBRL audit tests.
- CI success is not a live EOD or morning run and does not prove provider availability or complete market data.

## Shared cache and isolation
- Shared production inputs are read-only seed data only. ECMS-owned fundamental cache, state, diagnostics and reports stay isolated under `data/cache/ecms/` and `outputs/ecms/`.
- Never modify `.github/workflows/nse-test-scheduled.yml`, production scanner logic or shared cache contents as part of ECMS work.
- A restored cache is not proof that required files or fresh candidate metrics are present.

## Operational safety
- Research/shadow-only. No broker integration, order placement, automatic buy/sell or automatic buy instructions.
- Feed failure, empty response, HTML challenge, stale data, symbol mismatch, missing filing, incomplete provenance or incomplete XBRL evidence must remain `WAIT_FOR_DATA` or an explicit failure.
- No forced shortlist. Zero strong candidates is a valid result.
