# NSE V8 Full Mainboard Cohort — Artifact Schema & Coverage Audit (2026-11-10)

## Scope and provenance

This is an observational audit of the existing EOD report artifact. It does not change scanner selection, any production gate, ranking, Telegram output, or Track 1 / Track 2 behaviour.

- Repository: `digitalmf78-pixel/AI-Trading-Bot`
- Artifact: `nse-v8-reports-42774048772.zip`
- GitHub Actions run: `42774048772`
- Artifact ID: `13743417315`
- Artifact digest: `sha256:fba492126ffd1625bfa3d0a3c51964946707b78ca2cd083c7246aea2666ef6d0`
- Artifact source branch: `main`
- Artifact source commit: `b1505af3759dccd5131c0a3c51964946707a9cb9`
- EOD data date represented by the reports: `2026-11-09`

Counts below were read from the CSV files inside this artifact, not inferred from current branch source.

## Canonical cohort source

### Official Main Board classification

File: `outputs/v8_main_board_universe_audit.csv`

Columns:
- `TckrSymb`
- `BoardClassification`
- `MainBoardStatus`
- `ClassificationSource`

Rows: 3,037 unique symbols, no duplicate symbol keys:
- `PASS_MAIN_BOARD`: 2,588
- `EXCLUDED_SME`: 449

### Canonical full candidate frame for this artifact

File: `outputs/v8_delivery_dual_category_audit.csv`

Rows: 2,588; unique symbols: 2,588; duplicate symbol keys: 0.
Series:
- `EQ`: 2,385
- `BE`: 203

The 2,588 symbols in this file match the 2,588 `PASS_MAIN_BOARD` symbols exactly:
- PASS Main Board symbols missing from this frame: 0
- Frame symbols outside PASS Main Board: 0

This file is the correct artifact-level cohort base for assembly because it carries the full candidate EOD/security fields plus the full Delivery A/B audit. The four-column Main Board audit alone is not sufficient as a snapshot base because it does not carry the EOD market fields. The base already contains native Delivery columns, including:
- `DeliverySessions`, `DeliveryExpectedSessions30D`, `DeliveryCoveragePct`
- `AvgDelivery30D`, `LatestDeliveryPct`
- `DeliveryCategoryAStatus`, `DeliveryCategoryBStatus`, `DeliveryFilterStatus`
- dated delivery observations and delivery-quantity/consistency fields.

Observed Delivery status:
- A/B union `PASS_A_OR_B`: 758
- `FILTERED_OUT_A_AND_B`: 1,615
- `WAIT_FOR_DATA`: 215
- Category A pass: 758
- Category B pass: 102
- A_ONLY: 656
- A_AND_B: 102
- B_ONLY: 0

Therefore, do not replace this cohort base with the 758-row A/B union or any later shortlist.

## One-to-one stage report schemas and observed coverage

All listed one-to-one stage files have unique `TckrSymb` keys in this artifact, and none contains a symbol outside the 2,588-symbol Main Board cohort.

| Stage | Artifact file | Rows / unique symbols | Cohort symbols without a row | Important native fields |
|---|---|---:|---:|---|
| RVOL (all A/B candidates) | `outputs/v8_delivery_qualified_all_rvol_classified.csv` | 758 / 758 | 1,830 | `RVOL`, `RVOLStatus`, `RVOLBand`, `RVOLThresholdStatus` |
| Potential Accumulation | `outputs/v8_hybrid_potential_accumulation_watchlist.csv` | 758 / 758 | 1,830 | `WatchlistStatus`, `WatchlistReason`, `DeliveryEvidenceStatus` |
| Base/VCP | `outputs/v8_hybrid_base_vcp_watchlist.csv` | 758 / 758 | 1,830 | `VCPObservationStatus`, `VCPStatus`, `WatchlistStatus`, `WatchlistReason` |
| Liquidity | `outputs/v8_liquidity_first_audit.csv` | 758 / 758 | 1,830 | `LiquiditySessions`, `AvgDailyTradedValue20D`, `LiquidityStatus`, `LiquidityFilterStatus`, `LiquidityTier` |
| Fundamentals | `outputs/v8_fundamental_report.csv` | 54 / 54 | 2,534 | `FundamentalStatus`, `FundamentalAssessmentStatus`, `FundamentalReason`, scores and evidence fields |
| Technical | `outputs/v8_technical_report.csv` | 54 / 54 | 2,534 | `CoreTechnicalScreenStatus`, `CandidateScreenStatus`, technical and setup fields |
| Breakout Ready | `outputs/v8_hybrid_breakout_ready_watchlist.csv` | 54 / 54 | 2,534 | `WatchlistStatus`, `WatchlistReason`, breakout/pullback/chase fields |
| Confirmed Entry | `outputs/v8_hybrid_confirmed_entry_watchlist.csv` | 54 / 54 | 2,534 | `WatchlistStatus`, `WatchlistReason`, final confirmation fields |
| EOD Watchlist | `outputs/v8_eod_watchlist.csv` | 54 / 54 | 2,534 | `EODWatchlistStatus`, `EODWatchlistReason` |
| Risk Control | `outputs/v8_risk_control_report.csv` | 54 / 54 | 2,534 | `RiskControlStatus`, `RiskRewardStatus`, reasons and risk-plan fields |

### RVOL detail

The full 758-row Delivery-qualified classification file is required for RVOL coverage; the 105-row `v8_rvol_gt_1_5_candidates.csv` alone is only a positive subset and is not a complete RVOL stage report.

Observed RVOL distribution in the 758 A/B candidates:
- HIGH, `RVOL > 1.5`: 105
- LOW, `RVOL <= 1.5`: 610
- `WAIT_FOR_DATA`: 43

RVOL remains informational as defined in the master rules; do not interpret the missing 1,830 rows as RVOL rejection. Those symbols did not enter the A/B-qualified RVOL stage.

### Native status values are not interchangeable

Preserve each source status verbatim under a stage namespace. Examples:
- Potential Accumulation: all 758 rows say `ACCUMULATION_WATCH`; this is not a measured Sideways/Dip classification.
- Base/VCP: `BASE_FORMING` 68, `NO_SETUP` 432, `WAIT_FOR_DATA` 258.
- Breakout Ready: `ENTRY_CANDIDATE` 26, `NO_SETUP` 15, `CHASED` 6, `WAIT_FOR_DATA` 5, `BREAKOUT_CONFIRMED` 1, `PULLBACK_CONFIRMED` 1.
- Confirmed Entry: `WAIT_FOR_DATA` 29, `NO_SETUP` 19, `CHASED` 6.
- Fundamentals: `COMPLETE` 31, `PARTIAL_DATA` 23.
- Core Technical: `PASS` 3, `REJECT` 51.
- EOD Watchlist: `SKIP` 52, `WAIT_FOR_DATA` 2.
- Risk Control: `REJECT` 46, `WAIT_FOR_DATA` 5, `PASS` 3.
- Risk/Reward: `FAIL` 40, `WAIT_FOR_DATA` 6, `PASS` 8.

A row absent from a downstream report must be represented as coverage `NOT_EVALUATED` with a missing-source reason, not a synthesized PASS/REJECT. The coverage summary is not a new eligibility gate.

## One-to-many evidence sources

These must remain separate evidence tables; never merge them directly into the one-row-per-symbol cohort.

### News evidence

Use `data/inputs/news_evidence_auto.csv`, not `data/inputs/news_evidence.csv` (the latter is empty in this artifact).

Columns:
- `TckrSymb`, `PublishedAt`, `Headline`, `Source`, `SourceType`, `URL`, `Impact`, `EventID`, `SourceDomain`

Rows: 293; 48 unique symbols; 245 repeated-symbol rows; all 48 symbols belong to the Main Board cohort. Preserve all 293 rows.

### Corporate events

File: `outputs/v8_upcoming_corporate_events.csv`

Columns:
- `EODDate`, `TckrSymb`, `EventType`, `EventDate`, `AnnouncementDate`, `Headline`, `Source`, `SourceType`, `URL`, `Status`, `LookbackDays`

Rows: 246; 54 unique symbols; 192 repeated-symbol rows; all symbols belong to the Main Board cohort. Preserve all 246 rows separately. Observed status counts: `OFFICIAL_DATE_CONFIRMED` 6, `DATE_NOT_FOUND_OR_NO_FUTURE_DATE` 232, `NO_MATCHING_UPCOMING_EVENT_FOUND` 8.

## Join and identity contract

1. The scanner currently drops duplicate rows by `TckrSymb` in the prepared equity frame before applying the official Main Board filter. The observed full Main Board frame has one row per symbol and contains `SctySrs` values EQ/BE.
2. For this current source contract, the cohort identity is normalized `TckrSymb`; duplicate symbol rows fail closed. Do not silently switch to symbol+series without changing the scanner contract.
3. If both the cohort and a one-to-one stage report contain `SctySrs`, their normalized series values must match; mismatches fail closed.
4. One-to-one stage reports are left-joined onto the fixed 2,588-row cohort. No downstream report can add or remove cohort members.
5. News and corporate-event rows are separate one-to-many evidence tables with per-row `SOURCE_ROW_PRESENT` / `OUT_OF_COHORT` coverage.
6. Preserve raw source columns and native status/reason strings. Namespacing avoids collisions; no common status is invented.
7. Keep all assembly observational. Do not wire it into production until the source-to-output contract, tests, and workflow staging rules are separately reviewed.

## Current implementation status

- `signal_cohort_assembly.py` contains pure assembly helpers and separate news/corporate-event evidence outputs.
- `test_signal_cohort_assembly.py` covers cohort preservation, missing/empty reports, duplicate keys, raw status preservation, out-of-cohort diagnostics, one-to-many news/events, and series mismatch fail-closed behaviour.
- The module and tests are registered in `.github/workflows/nse-v8-ci.yml`.
- Actual artifact schemas and cohort coverage counts have been audited as above.
- Python unit tests / GitHub Actions CI have not yet been executed for these new changes.
