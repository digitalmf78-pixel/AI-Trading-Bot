# NSE V8.0 — Step 1 Signal Log Code Mapping
**Date:** 10-Nov-2026  
**Branch:** `audit/implementation-roadmap-2026-11-10`  
**Status:** Source mapping completed; implementation boundary and unresolved items recorded.  
**Related design:** `NSE_V8_SIGNAL_LOG_SHADOW_RUN_DESIGN_2026-11-10.md`

## 1. Canonical EOD candidate cohort

### Verified source
- `volume_gainer.py` calls `get_latest_eod()`, then `prepare_equity_data(raw_current)`.
- `apply_official_main_board_filter(current)` returns:
  - filtered Mainboard dataframe for downstream processing;
  - `board_audit` with `TckrSymb`, `BoardClassification`, `MainBoardStatus`, `ClassificationSource`.
- `main_board_filter.py::apply_main_board_filter()` explicitly marks `PASS_MAIN_BOARD`, `EXCLUDED_SME`, and `EXCLUDED_UNVERIFIED_CLASSIFICATION`.
- `delivery_filter.py::apply_delivery_filter()` creates one audit row for each supplied Mainboard candidate and returns the full audit, including Delivery PASS, filtered-out, and WAIT statuses when report data is available or fewer than five valid reports are available.
- The scanner writes `outputs/v8_delivery_dual_category_audit.csv`; this is the best current persisted full-cohort report when the Delivery stage completes normally.

### Proposed canonical cohort rule
Use all unique symbols with `MainBoardStatus == PASS_MAIN_BOARD` from `board_audit` as the authoritative eligible-universe key set. Enrich those keys with the matching full Delivery audit row and later reports using a left-join keyed by normalized symbol plus series where available. Never use the A/B union, RVOL HIGH subset, Liquidity PASS subset, Technical subset, or final shortlist as the snapshot cohort.

Why: downstream reports are progressively narrower; anchoring on any later report would silently omit valid earlier-stage candidates. SME and unverified-board symbols remain outside the eligible candidate cohort, but their board-classification audit can be retained as separate universe diagnostics if explicitly needed.

### Important failure-path gap
If an unexpected exception escapes the Delivery block, `volume_gainer.py` currently sets `current` to an empty dataframe and assigns an empty `delivery_audit`. The original `board_audit` still has the Mainboard symbol keys, but not the prepared EOD price/volume columns. A complete snapshot cannot be built from CSV reports alone in that failure path.

**Required observational-only source hook:** capture a sanitized copy of the prepared Mainboard dataframe immediately after successful Mainboard classification, before Delivery processing, as a dedicated signal input report (or pass it in memory to the shadow builder). This must be a copy only and must not be assigned back to `current` or alter the scanner flow. If Mainboard classification itself fails, create a manifest with an explicit universe `WAIT_FOR_DATA` status; do not fabricate candidates.

## 2. Stage-to-source mapping

| Stage | Existing source | Key status fields | Cohort behavior |
|---|---|---|---|
| Raw EOD / Mainboard | `board_audit`; prepared Mainboard frame currently in memory | `MainBoardStatus`, `BoardClassification` | Defines eligible candidate keys |
| Delivery 30D A/B | `outputs/v8_delivery_dual_category_audit.csv` | `DeliveryCategoryAStatus`, `DeliveryCategoryBStatus`, `DeliveryFilterStatus`, `DeliveryStatus` | Full Mainboard cohort when report stage runs |
| RVOL | `outputs/v8_delivery_qualified_all_rvol_classified.csv`; HIGH/LOW/WAIT split reports | `RVOLBand`, `RVOLThresholdStatus`, `RVOL` | A/B union only; left-join; absence for non-A/B is not a status |
| Early Accumulation / Base-VCP | generated through `write_early_hybrid_watchlists()` | `WatchlistStatus`, `WatchlistReason`, module-specific evidence statuses | Independent A/B-union observations; missing row means not evaluated/not produced, not REJECT |
| Liquidity 20D | `outputs/v8_liquidity_first_audit.csv` | `LiquidityStatus`, `LiquidityFilterStatus`, `LiquidityTier` | A/B union, including PASS/REJECT/WAIT |
| Fundamentals | `outputs/v8_fundamental_report.csv` | `FundamentalStatus`, `FundamentalReason`, metric verification fields | Liquidity-qualified cohort; missing row means not evaluated |
| Technical / RS / Core screen | `outputs/v8_technical_report.csv`; `outputs/v8_liquidity_technical_fundamental_report.csv`; technical parameter audit | setup, trend, breakout/pullback, `CoreTechnicalScreenStatus`, RS fields | Liquidity-qualified cohort / technical analysis subset as defined by current selector; absence must not be interpreted as fail |
| News / events | `auto_news` plus `outputs/v8_upcoming_corporate_events.csv` and related reports | source, verification, event date/status | Evidence rows may be zero-to-many per symbol; preserve as linked evidence, not one flattened status |
| Sector / later V8 layers | `result` after `run_eod_layers()`; `outputs/v8_layer_status_summary.csv` | per-layer statuses, sector status, confirmation statuses | Current result cohort; left-join to canonical cohort |
| Risk / final | `outputs/v8_risk_control_report.csv`, `outputs/v8_eod_watchlist.csv`, `result` | `RiskControlStatus`, `RiskControlReason`, `RiskRewardStatus`, `EODWatchlistStatus`, `EODWatchlistReason` | Later-stage subset; missing row is not a rejection |

## 3. Existing selection-audit limitation
The current `v8_selection_status_report.csv` is built by concatenating Delivery, Liquidity, Fundamental, Portfolio Risk and Final EOD frames. It does not include a complete, normalized stage-event record for Mainboard, RVOL, early watchlists, Core Technical, sector/news/3+1, or all intermediate layer statuses. It is useful as an input, but it is not a complete event log and must not be treated as one.

The shadow builder should create stage events from the original source reports independently and preserve source-specific status/reason columns. Do not coerce module-specific statuses into a fabricated common PASS/REJECT meaning.

## 4. Entry / stop / target source mapping
- In `v8_layers_14_41.py::run_eod_layers()`, `EntryPricePlan` is assigned from `EntryZoneHigh`.
- `StopLossPlan`, `TargetPricePlan`, `TargetSource`, `StructuralResistanceUsed`, `StructuralResistanceSource`, `RiskReward`, and `RiskRewardStatus` are produced by the existing risk/reward calculations.
- A missing verified structural resistance can result in `WAIT_FOR_DATA`; no synthetic 2R target is created.
- Preserve these values exactly as observed at EOD. Shadow logging must not recalculate or repair entry/stop/target proposals.

## 5. Sensitive-field and artifact ordering
- `sanitize_public_artifacts.py` removes `ProposedPositionQty`, `RiskBudgetINR`, and `ProposedExposurePct` from report CSVs before public artifact upload.
- The EOD workflow currently runs Fundamental Cache persistence before report sanitization, then uploads artifacts after sanitization.
- The signal snapshot must explicitly exclude those account-derived fields and all secret/config data, regardless of the sanitizer.
- If shadow records are built from CSV artifacts, build them only after successful sanitization, or pass a separately allow-listed payload to the shadow module. Never serialize the entire `result` dataframe without a strict field allow-list.
- The existing Fundamental Cache commit stages only its own explicit files. Shadow persistence must stage only `data/signals/**`; never use `git add .` or broad `outputs/**`.

## 6. Workflow integration boundary
Current workflow: `.github/workflows/nse-test-scheduled.yml`.
- Scheduled EOD scan runs at 16:40 UTC (22:10 IST) Monday–Friday; 02:30 UTC (08:00 IST) is PREMARKET mode.
- The workflow has `permissions: contents: write`, branch-scoped concurrency, a successful-scan-gated Fundamental Cache commit, artifact sanitization, and report upload.
- Shadow snapshot generation/persistence must run only when `NEWS_SCAN_MODE == EOD` and the scanner step succeeded.
- It must not run during PREMARKET refresh.
- It should be placed after `artifact_redaction` succeeds, before artifact upload, and must be a separate step with explicit `data/signals/**` staging only.
- The current workflow is scheduled on main; a manual run can target the working branch. Verify branch protection and workflow permissions before enabling writes. Do not change the main workflow or merge this audit branch as part of this mapping task.

## 7. Outcome calculation mapping
- `nse_trading_calendar.py` provides official session validation and raises `CalendarCoverageError` for unconfigured years.
- The scanner loads historical Bhavcopy through `collect_historical_days(eod_date, HISTORY_DAYS)`; the workflow validates and restores `data/bhavcopy/`.
- Outcome horizons must count distinct official sessions strictly after signal EOD date.
- Outcome price source should be validated Bhavcopy OHLC with unique date/symbol records. Duplicate or missing OHLC rows must cause a coverage status, not silent averaging.
- Entry reference in the design remains the signal EOD close for research measurement only, explicitly not a simulated fill.
- The repository currently has no signal-level 5/10/20 horizon tracker or MFE/MAE calculation identified in the inspected source tree.

## 8. Implementation order after this mapping
1. Add a pure, independently testable shadow-store module that consumes explicit input dataframes/records and writes only to a temporary/test path by default.
2. Add schema, canonical serialization, stable ID/hash, exact duplicate no-op and changed-payload conflict tests.
3. Add cohort assembly tests using Mainboard, Delivery, Liquidity, Fundamental, Technical and Final fixture reports; assert left-join behavior and preservation of early candidates.
4. Add point-in-time and redaction allow-list tests.
5. Add outcome calculator tests using synthetic OHLC and official calendar fixtures.
6. Only after module tests pass, add the minimal in-memory prepared-Mainboard source hook and a separately gated EOD workflow step on the working branch.
7. Run existing CI and a real EOD shadow-only validation; compare all production reports before/after and verify no selection or Telegram behavior changed.

## 9. Explicit unresolved items
- Whether symbol + series is sufficient canonical instrument identity across corporate actions/name changes; inspect NSE security identifiers before implementation.
- Whether source CSVs are retained unmodified until after shadow snapshot generation; current artifact sanitizer edits selected report files in place.
- Exact set of fields allowed in the point-in-time snapshot must be finalized as a strict allow-list from actual source columns.
- Whether all intermediate layer statuses are present in one output or need to be extracted from the final `result` dataframe; verify actual report columns and row-level coverage.
- Branch protection / GitHub Actions write permission behavior on the working branch.
- Outcome correction/revision policy for a previously persisted partition.

---
**Change control:** Mapping only. No Python scanner code, workflow, selection gate, risk formula, Telegram message, Master Specification, or main-branch file has been changed.
