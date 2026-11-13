# V9 Baseline Audit — NSE Swing Trading Scanner
**Audit date:** 13-Nov-2026  
**Repository:** `digitalmf78-pixel/AI-Trading-Bot`  
**Audited base:** `main` at `fa45a98b162f3c4ad5f00bfa5258b4323e732aaa`  
**Scope:** Read-only code, workflow, parameter-register and validation-document inspection.  
**Change boundary:** This document only. No production Python, YAML, thresholds, Telegram behaviour or trading rules were changed.

## 1. Executive summary

The repository already contains a substantial V8 research scanner. It is not an empty/early project and should not be rewritten as V9. V9 should be an incremental, evidence-led extension that preserves the current production Track 1 and independent Track 2 boundaries.

The latest `main` commit inspected was created by GitHub Actions on 13-Nov-2026 and persists fundamental cache/history artifacts. The connected GitHub identity has push permission. This audit was committed only to a new audit branch; it was not merged into `main`.

## 2. Current production rules verified in code/docs

### Universe
- Eligible NSE Mainboard Largecap, Midcap and Smallcap securities.
- SME, ETF and Mutual Fund instruments are excluded.
- Mainboard classification is official-source based; unknown/unverified classifications fail closed.
- The scanner is EOD research/analysis and does not place orders.

### Delivery A/B — latest approved rule in the working parameter register
- Lookback: 30 calendar days ending on the EOD as-of date; use every valid, distinct, candidate-specific NSE Delivery report in that window.
- Minimum coverage: five valid reports; fewer or stale/unavailable data = `WAIT_FOR_DATA`.
- Category A: calculate every trailing five-valid-session rolling average in the window; count windows with average Delivery % >=60%. A passes when at least five such windows qualify.
- Category B: count individual daily Delivery observations >=60% in the same window. B passes when at least five qualifying days exist.
- Production eligibility is A OR B; preserve A_ONLY / B_ONLY / A_AND_B and deduplicate.
- The older strict interpretation “each of the last five days must be >=60%” is not the active production rule. Five-/ten-/twenty-session observations may be reported separately but must not silently replace A/B.
- Source files: `delivery_filter.py`, `delivery_categories.py`, `NSE_V8_HYBRID_STRATEGY_MASTER_PARAMETERS_2026-11-09.md`.

### RVOL
- Calculated only after the full Delivery A/B union exists.
- Baseline uses exactly 20 prior complete, distinct sessions; current EOD session excluded.
- >1.5 = HIGH; <=1.5 = LOW; missing/invalid = WAIT_FOR_DATA.
- RVOL is informational/classification only. HIGH, LOW and WAIT candidates continue to Liquidity. No Top-20/Top-50 cap.
- Source: `volume_gainer.py`, `test_selection_pipeline_order.py`.

### Liquidity
- 20 prior complete sessions, using NSE CM Bhavcopy `TtlTrfVal`.
- Hard minimum = ₹1.5 crore average daily traded value.
- Tiers: LOW ₹1.5–<₹2 crore; MEDIUM ₹2–<₹5 crore; STRONG >=₹5 crore.
- ₹5 crore is a tier boundary, not the hard minimum. Do not raise the ₹1.5 crore gate without explicit approval.
- Missing/duplicate/invalid sessions or symbol values = WAIT_FOR_DATA.
- Source: `liquidity_filter.py`, `test_liquidity_filter.py`.

### Fundamentals
- Collection occurs after Liquidity for every liquidity-qualified candidate.
- Current fundamental score/data status is enrichment, classification, priority and risk context—not a hard rejection gate.
- Official NSE filings/XBRL are verification sources; provider values are not official until exact symbol, period and publication/as-of alignment are reconciled.
- Missing, stale, conflicting or incomplete metrics remain visible; they must not be guessed or silently used to reject a candidate.
- Source: `fundamental_filter.py`, `fundamental_data_provider.py`, `fundamental_shortlist.py`, README and working parameter register.

### News, sector, technical and risk
- Existing news/catalyst, sector mapping, price/volume, breakout/pullback, support/resistance, mandatory confirmation and portfolio risk modules are present and must be preserved.
- The V8 layer module explicitly uses `WAIT_FOR_DATA` when required evidence is absent and does not turn a score into an automatic order.
- Portfolio risk controls require a valid risk configuration and verified exposure/position inputs; missing configuration should remain WAIT_FOR_DATA, not assume a four-position cap or zero exposure.
- Do not infer institutional buyer identity from Delivery data. Use “Potential Accumulation Evidence”, not “institutional accumulation confirmed”.

## 3. Hybrid/Track 2 capabilities and current limitations

### Already present
- Delivery Quantity 5/10/20 report-session observations.
- Potential Accumulation observations, including rolling price ranges, pivots/Higher-Low, delivery/volume and price-response context.
- Three-block VCP observer (three consecutive 20-session blocks).
- EMA20/44/50/200 observations.
- Separate Potential Accumulation, Base/VCP, Breakout Ready and Confirmed Entry watchlist outputs.
- Ten-trading-session post-breakout follow-through/retest observations.
- Track 2 full-Mainboard observer is wired to the EOD flow and writes to its own output namespace; it must not change Track 1 eligibility.

### Not yet a confirmed classifier / pending definitions
- Fixed-Range Base does not yet identify algorithmic base start/end boundaries; rolling 20/50/100/200 windows are observations, not a detected base.
- VCP output is descriptive. `BASE_FORMING` means two successive contractions were observed and explicitly says NOT_VCP_CONFIRMED. Do not call it confirmed VCP.
- SIDEWAYS_ACCUMULATION and DIP_ACCUMULATION are not classified yet.
- Pocket Pivot detector/formula is not implemented/approved.
- False-breakout failure/re-entry definitions, retest buffer, support/resistance zone clustering tolerance, and final VCP/base thresholds remain pending.
- The 0.5x volume dry-up marker is observational only, not a filter or entry condition.

### Track 2 historical data evidence (EOD 09-Nov-2026)
The recorded offline validation reconciled the full eligible cohort at 2,588/2,588 unique Mainboard symbols. It reported:
- Delivery Quantity: 2,253 COMPLETE / 335 WAIT.
- Potential Accumulation: 2,253 observations available / 258 partial / 77 WAIT.
- VCP: 2,023 COMPLETE / 565 WAIT.
- Pivot/EMA observations: 1,665 COMPLETE / 923 WAIT.
These are dated historical artifact results, not today's live counts. The next task is to classify and reduce genuine data-coverage gaps without weakening completeness rules.

## 4. Outcome tracking and win-rate evidence

- `signal_outcome_tracker.py` records next official session Open as a research entry reference and tracks 5/10/20-session raw price outcomes plus MFE/MAE when complete.
- The code explicitly labels this as a research reference, not an actual fill.
- Fees/slippage are currently `NOT_CONFIGURED`.
- Therefore, the repository does not yet prove a live/validated net win rate, net expectancy or after-cost profit factor. Do not advertise a “win-win rate” based only on raw price movement.
- Next requirement: configure realistic brokerage/taxes/slippage assumptions, define trade exits and position lifecycle, then run point-in-time walk-forward/out-of-sample evaluation with adequate closed-trade sample size.

## 5. CI/workflow status found

- `.github/workflows/nse-test-scheduled.yml` has weekday EOD and premarket schedules, manual dispatch modes and push-triggered validation for listed source paths.
- The workflow checks required files, Python compilation and multiple unit/regression suites; it has a 75-minute timeout and contents write permission for persistence.
- The repository documentation records a Track 2 offline validation over 2,588 Mainboard symbols and CI evidence of 403 pytest tests, 33 V8 regression tests and 43 sector/news/official-index tests passing on the documented run.
- README's “Latest audited run” funnel is still dated 10-Nov-2026 (run 42774048772). The latest inspected main commit is a 13-Nov cache-persistence commit. A fresh current EOD run/artifact review is still required before claiming current operational status.

## 6. Priority gap matrix

| Priority | Gap / task | Recommended action | Do not do |
|---|---|---|---|
| P0 | Current production baseline is not backed by a fresh 13-Nov EOD artifact review in this audit | Inspect latest Actions run, artifacts, logs and stage counts | Do not infer current counts from 10-Nov README |
| P0 | Outcome tracking has no costs/slippage configured | Configure explicit cost model and distinguish research reference from fill | Do not claim net win rate/profitability yet |
| P0 | Point-in-time performance validation is incomplete | Build/verify chronological walk-forward and untouched out-of-sample reports | Do not tune on the final test period |
| P1 | Track 2 has meaningful symbol/session WAIT coverage | Audit missing sessions by source, symbol, series and module; backfill only from official data | Do not relax completeness rules or replace missing values |
| P1 | Fundamental quality needs better usable ranking while preserving the approved collection boundary | Improve metric provenance/coverage and build a transparent sector-aware priority score as non-gating research first | Do not add a hard Fundamental reject gate without approval and evidence |
| P1 | News/event source freshness and horizon need verification | Audit current RSS/official filing lookback, event horizon, deduplication and revision history | Do not treat unverified headlines as confirmed catalysts |
| P1 | Hybrid watchlists are descriptive, not fully classified | Implement objective Fixed-Range Base and VCP definitions only after thresholds are agreed/tested | Do not rename BASE_FORMING as confirmed VCP |
| P2 | SIDEWAYS/DIP and Pocket Pivot are undefined | Keep as pending research items; prepare candidate definitions for review | Do not invent numeric thresholds/formulas |
| P2 | Branch drift / parallel experiments | Compare each branch to current main; cherry-pick/rebase one focused patch at a time | Do not merge entire stale/diverged branches |

## 7. Git branch safety findings

Several active branches differ materially from current `main` and are behind it. Examples observed during comparison:
- `feat/telegram-summary-report-mode-2026-11-13`: 8 commits ahead, 2 behind; touches Telegram/news/workflow files.
- `fix/eod-workflow-timeout-and-signal-persistence-2026-11-13`: 1 ahead, 10 behind; touches workflow YAML.
- `fix/backtest-delivery-date-integrity-2026-11-13`: 2 ahead, 4 behind.
- `audit/fixed-range-vcp-implementation-2026-11-11`: 4 ahead, 139 behind.
These are not safe to merge wholesale. Rebase/update against current main, inspect the exact diff, run relevant tests, then open a focused PR.

## 8. V9 work order

1. Freeze current V8 `main`; preserve its current Delivery A/B, RVOL, Liquidity, Fundamental collection boundary, news/sector/technical confirmations and risk controls.
2. Capture a fresh baseline: latest workflow run, exact EOD date, artifact list, stage funnel, missing-data reasons and Telegram/workflow status.
3. Complete the canonical point-in-time signal/outcome contract; configure costs/slippage and real trade lifecycle assumptions.
4. Audit Track 2 2,588-symbol cohort and per-module missing-session coverage; make a source-backed coverage/backfill plan.
5. Improve fundamental provenance, coverage and sector-aware ranking as non-gating enrichment.
6. Audit news/catalyst freshness, event horizon, deduplication/revisions and report output.
7. Define and test Fixed-Range Base, VCP, SIDEWAYS/DIP, Pocket Pivot and false-breakout/retest semantics; keep observations non-gating until validated.
8. Run historical walk-forward/out-of-sample tests, cost sensitivity and market-regime/setup breakdown.
9. Paper trade the validated signal process; compare research reference prices with realistic next-session fills.
10. Only after user approval, integrate a single tested patch into production.

## 9. Non-negotiable guardrails

- Do not replace 30-day Delivery A/B with “each of last five sessions >=60%”.
- Do not change Liquidity hard minimum from ₹1.5 crore to ₹5 crore; ₹5 crore is a STRONG tier.
- Do not use RVOL as a rejection gate or reintroduce Top-20/Top-50 caps.
- Do not reject on missing fundamental/news/sector/price data; use the correct WAIT_FOR_DATA status.
- Do not make Fundamental score a hard gate without a separately approved, tested decision.
- Do not force four stocks into the final list.
- Do not infer institutional buyer identity from Delivery %.
- Do not treat observational labels as BUY/ENTRY signals.
- Do not invent pending VCP, base, Pocket Pivot, retest or false-breakout thresholds.
- Do not merge parallel branches wholesale.
- Do not commit secrets, API tokens, Telegram credentials or private risk configuration.
- Do not place real orders; this repository is a research/analysis scanner.

## 10. Audit conclusion

**Recommendation: V9 should be an incremental research-and-validation release, not a rewrite.** First priority is current EOD evidence + cost-aware outcome measurement + Track 2 data coverage. Then improve fundamental/news/sector evidence and formalize hybrid pattern definitions. Preserve V8 production gates until a specific, tested change is approved.
