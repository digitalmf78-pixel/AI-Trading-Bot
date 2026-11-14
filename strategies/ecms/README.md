# ECMS — EOD Catalyst Momentum Scanner

An isolated research module inside AI-Trading-Bot. The current implementation is EOD-only and does not modify or replace the existing NSE V8 production scanner.

## Current implementation status
- **EOD module:** implemented in `strategies/ecms/eod.py`.
- **Manual workflow:** `.github/workflows/ecms-eod-shadow.yml` (`workflow_dispatch` only).
- **Unit tests:** `tests/test_ecms_eod.py` (written; not yet executed in GitHub Actions).
- **Morning workflow:** not implemented.
- **Automatic schedules:** disabled.
- **Broker orders:** not supported; no auto-buy or auto-sell.

## EOD pipeline
1. Read the latest complete Bhavcopy session from the shared cache and require it to match the latest completed NSE session.
2. Require 20 prior complete sessions; calculate full-session RVOL against the prior 20-session average.
3. Apply the repository's listed-equity series allowlist, exclude ETF/mutual-fund-like rows, then use fresh official NSE Main Board and SME lists to exclude SME/unverified symbols.
4. Keep RVOL >= 1.5 as an initial research threshold. It is a configurable research hypothesis, not a validated trading edge.
5. Read cached fundamentals, official financial-result filing metadata, the evidence ledger and already cached XBRL files. Build metric verification locally without downloading or changing shared data.
6. Check the trailing five calendar days of issuer-matched NSE announcements and secondary news. Mark strong positive headline signals and negative-risk signals for manual review; keyword triage is not proof of financial impact.
7. Only mark `EOD_RESEARCH_SHORTLIST` when the fundamental gate passes, the source checks are available, a strong positive catalyst signal exists and no negative-risk keyword was detected. All other rows retain explicit `WAIT_FOR_DATA`, `NOT_QUALIFIED` or review statuses.

## Fundamental verification limitation
The existing fundamental gate requires every required metric to be verified against official XBRL evidence. The repository currently has approved evidence mappings for only a subset of the required metrics; unsupported derived ratios remain `WAIT_FOR_DATA`. Do not weaken this gate just to force a shortlist. A separate audited derivation/mapping is needed before those metrics can pass.

## Data boundaries
- Shared data is read-only: `data/bhavcopy/`, the shared `data/cache/` paths, `data/inputs/fundamental_metrics.csv`, `data/inputs/fundamental_thresholds.json`, `data/inputs/fundamental_metric_verification_evidence.csv`, and `outputs/v8_official_financial_results_filings.csv`.
- The EOD workflow restores the same ordered shared-cache paths and uses restore prefixes compatible with the production cache.
- ECMS writes reports only beneath `outputs/ecms/`; it does not save back into shared cache, metrics, filing registers or evidence ledgers.
- Existing `.github/workflows/nse-test-scheduled.yml`, scanner code and production outputs remain untouched.

## Output reports
- `outputs/ecms/eod_candidates.csv` — RVOL candidates with fundamental, catalyst and final statuses.
- `outputs/ecms/eod_audit.csv` — Main Board inclusion/exclusion and candidate audit.
- `outputs/ecms/eod_catalysts.csv` — issuer-matched headline records and signal labels.
- `outputs/ecms/fundamental_metric_verification.csv` and summaries.
- `outputs/ecms/eod_run_summary.json`.

## Later phase — Morning confirmation
Morning monitoring is intentionally not part of this phase. It will be built only after the EOD output is validated and a supported, timestamped live-market data source is verified. Volume Gainers presence will be optional confirmation, never a mandatory gate. The scan is expected to start at 09:15 IST and final confirmation not before 09:25–09:30 IST.

## Validation gates
The EOD workflow is manual/shadow-only. Execute tests and inspect the first real artifact before adding any schedule. Missing/stale Bhavcopy, calendar coverage, board lists, fundamentals, XBRL evidence or news source must remain visible as a failure or `WAIT_FOR_DATA`; never manufacture a pass.
