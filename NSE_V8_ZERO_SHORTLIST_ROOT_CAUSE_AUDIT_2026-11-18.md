# NSE V8 Zero-Shortlist Root-Cause Audit — 18-Nov-2026

## Scope and evidence boundary

This audit uses the completed NSE V8 EOD workflow **run 44201214580**, whose EOD data date was **17-Nov-2026**, and its uploaded report artifact. It is a verified single-run diagnosis, not yet a complete 30-calendar-day run-by-run reconciliation. No Master Specification, trading threshold, or Bhavcopy price-history file was changed.

## 1. The scanner did run and did collect candidates

| Stage | Verified result |
|---|---:|
| Full Mainboard Track 2 research cohort | 2,590 symbols |
| Delivery A/B union before Liquidity | 1,186 symbols |
| Liquidity PASS | 342 (223 STRONG, 88 MEDIUM, 31 LOW) |
| Liquidity REJECT | 795 |
| Liquidity WAIT_FOR_DATA | 49 |
| Fundamental collection | 342 rows; enrichment only |
| RVOL | Classification only; all Delivery A/B names continued to Liquidity |
| Final EOD entry shortlist | 0 |

The 342 Liquidity-PASS candidates were not lost at the Delivery, RVOL, Liquidity, or Fundamental-collection stages.

## 2. Verified primary cause of the zero final shortlist

The NSE V8 run attempted to refresh Nifty 50 history for EOD 17-Nov-2026. The Yahoo fallback response did not contain the exact 17-Nov close, so the scanner preserved its previous cache through **16-Nov-2026**. The log explicitly recorded that at least 21 valid Nifty closes ending exactly on 17-Nov were required for the 20-session benchmark return.

Consequences in the EOD artifact:

- Nifty 20D return and per-stock relative strength were unavailable for all 342 Liquidity-PASS candidates.
- Sector-strength status was WAIT_FOR_DATA for all 342.
- Market-regime status was WAIT_FOR_DATA for all 342.
- V8 score coverage was only 65/100 for 329 rows and 60/100 for 13 rows; no row reached 100% coverage.
- Maximum V8 score was 65; no candidate could reach the existing >=70 final score gate.
- Core technical PASS was 0/342 and final EOD shortlist was empty.

There were 20 rows whose only recorded core-screen reason was missing Relative Strength data. The remaining rows also had independent technical reasons such as no confirmed Breakout/Pullback setup, non-bullish trend, or selling/distribution. The Nifty data failure therefore blocked otherwise plausible setups as well as the downstream sector/regime/score calculations.

### Changes in this branch

1. Added an official NSE all-indices archive reader for Nifty 50 history. It requires 50 distinct official sessions including the exact requested EOD date, validates the internal archive date and exact Nifty 50 index name, and fails closed if coverage is incomplete.
2. The Nifty history cache is now stored separately at `data/cache/market_index/nifty50_index_history.csv`. The scheduled NSE V8 workflow persists this separate cache. Existing `data/bhavcopy/` price history is not modified or rewritten.
3. Yahoo remains a fallback only when the official NSE archive path is unavailable; stale data is never relabelled as current.
4. Corrected core-screen status semantics: missing required Relative Strength/Support-Resistance/Delivery data is WAIT_FOR_DATA when there is no independent hard technical rejection. A separate confirmed setup/trend/distribution failure remains REJECT.
5. Removed missing RVOL baseline as a core-screen rejection reason. RVOL is classification-only as specified; unavailable RVOL is recorded as a warning and does not itself reject a candidate. Other approved technical and final-entry gates remain unchanged.

## 3. The scanner has research candidates, but the compact Telegram summary hid them

The 17-Nov artifact contains these separate non-entry stages:

| Research stage | Rows |
|---|---:|
| Potential Accumulation Watch | 1,186 |
| BASE_FORMING observations | 106 |
| Breakout observations | 1 confirmed + 187 general Breakout/Pullback observations |
| Pullback observations | 14 confirmed |
| Final ENTRY_CANDIDATE | 0 |

The Telegram compact-summary selector previously included only final WATCH/ENTRY_CANDIDATE rows. Consequently, when final entries were zero, it displayed no stock names even though the research watchlists had candidates. The full audit document did contain the separate research sections.

### Changes in this branch

- When final WATCH/ENTRY_CANDIDATE rows exist, the existing final-only summary behavior remains unchanged.
- When no final entry exists, the compact summary now displays up to 10 clearly labelled research-only examples from Breakout/Pullback, BASE_FORMING, and Potential Accumulation stages.
- The summary reports stage counts and labels these examples **NOT BUY / NOT ENTRY**.
- CHASED, NO_SETUP, and WAIT_FOR_DATA rows are excluded from the research examples.
- No scanner membership, scoring, trading filter, ranking, or order eligibility is changed by this presentation fallback.

## 4. Separate five-session Delivery watchlist cache race

Workflow **44203237144** restored cache key **44069755492**. It successfully fetched five valid Delivery reports ending 17-Nov-2026, but the matching official Bhavcopy for 17-Nov was not yet in that restored cache. It therefore wrote an empty WAIT_FOR_DATA output. The NSE Data Test EOD workflow was still running at that time and saved its updated cache only later.

### Change in this branch

The five-session Delivery watchlist now runs after the successful completion of the NSE Data Test workflow, so it can restore the cache that the EOD run has just saved. Manual dispatch remains available. It no longer relies on a fixed clock time that can race the longer EOD workflow.

## 5. Other verified downstream gates (not relaxed)

On the same 17-Nov artifact:

- 3+1 mandatory confirmation: 9 PASS, 1 FAIL, 332 WAIT_FOR_DATA.
- Risk/Reward: 27 PASS, 298 FAIL, 17 WAIT_FOR_DATA.
- Risk control: 242 PASS, 100 REJECT.
- Chase guard: 307 CLEAR, 35 CHASE.
- Accumulation/Distribution: 329 had a measured status, 13 WAIT_FOR_DATA.

These gates must be re-evaluated after Nifty/sector/market data is restored. This patch does not lower their thresholds or manufacture an entry.

## 6. Still required in the broader NSE V8 audit

1. Run the full NSE V8 CI suite on this branch and resolve any failures before merge.
2. Run a fresh EOD after the official Nifty history fix and compare exact stage counts, Nifty/sector/market data coverage, score coverage, and final shortlist.
3. Reconcile the last 30 calendar days of EOD artifacts to establish whether the Nifty exact-date gap persisted every day or only in the latest available run.
4. Complete the Momentum/Trend audit: verify RSI remains informational, confirm EMA/ADX/price-volume roles, and ensure no unapproved momentum hard gate exists.
5. Keep Fixed-Range Base and final VCP classification as outstanding. Current code has rolling 20/50/100/200-session range observations, three-block VCP observations, and BASE_FORMING as an observation only. Do not invent base boundaries, contraction thresholds, VCP_CONFIRMED rules, or BUY gates without explicit approval.
6. Re-run the 5D/10D/20D delivery and price-response backtests only after exact-date source coverage is complete. Do not relax validation for speed.
7. Complete the risk/stop/target and signal-outcome audit against the current Master Specification; do not introduce synthetic 2R targets or alter the immutable Master Specification.

## 7. Safety and change control

- No changes to the immutable Master Specification.
- No changes to existing Bhavcopy price-history contents.
- No changes to Delivery A/B thresholds, Liquidity >= ₹1.5 Cr, or the RVOL classification-only rule.
- No Top-N cap added to the scanner.
- No BUY/ENTRY signal is generated from research-only watchlist rows.
- No unapproved Base/VCP thresholds or new technical gates are introduced.

**Current state:** fixes and regression tests are committed to the working branch. GitHub Actions validation and a fresh post-fix EOD result are still pending; this audit does not claim the scanner is already fixed in production.
