# ECMS Repository, Workflow and Data Audit — 16 November 2026

**Audit scope:** ECMS code paths, workflow files, tests, documentation and the latest available EOD/Morning artifacts.  
**Repository main at audit:** `9e4b722c2be223ffa8ec78df4a1c5aeb84e28794`.  
**Audit branch:** `research/ecms-roadmap-audit-first`.  
**Important evidence boundary:** The inspected live EOD artifact is Run #335, head `012bd9e79eaee71a385f4cbcae2c77949faa855b`, which predates PR #139. PR #139's scan-date, event/deal parsing and payload-diagnostic changes passed CI, but this audit did not find a post-PR-#139 live Morning/EOD artifact. Do not treat Run #335 as live validation of the current main code.

## 1. Executive findings

ECMS has a useful research foundation: Main Board filtering, separate Morning/EOD snapshots, strict session-date checks, 20-session Bhavcopy RVOL, seven-metric fundamental assessment, official XBRL verification, batch event/deal/corporate-action feeds, candidate-level reports and explicit source statuses.

However, the current system is **not yet an institutional-footprint, operator-trap or entry-readiness scanner**. The active Volume Gainers workflow does not currently collect delivery history, historical ownership changes, promoter pledge changes, official surveillance lists, or technical breakout/retest evidence. The existing `nse_shareholding.py` parser is not currently activated by the seven-metric ECMS collection request.

The highest-priority work is therefore not to add a score. It is to improve data coverage, provenance, historical storage, source freshness, cache isolation and report correctness first.

## 2. Confirmed operating baseline

### Active workflow

File: `.github/workflows/ecms-volume-gainers-shadow.yml`

- Morning cron: `50 3 * * 1-5` UTC = 09:20 IST.
- EOD cron: `30 11 * * 1-5` UTC = 17:00 IST.
- Manual dispatch supports `morning` and `eod`.
- Scan jobs have 10-minute timeouts; validation has 15 minutes.
- Main Board equity membership and official SME subtraction are applied before assessment.
- The page currently labels its table Top 25; ECMS processes rows returned by that page, not the entire NSE Main Board universe.
- The legacy `.github/workflows/ecms-eod-shadow.yml` has manual dispatch only, no cron. It is labelled “DO NOT USE” and checks out the old `ecms/phase-0-foundation` branch. It is not a third scheduled scan, but remains a potential manual-run confusion point.

### Comparison lifecycle

The current code keeps these responsibilities separate:

1. Previous valid EOD snapshot -> next trading-session Morning (for example Monday EOD -> Tuesday Morning; Tuesday EOD -> Wednesday Morning; and so on).
2. Same-session Morning snapshot -> same-session EOD.
3. Current valid EOD snapshot -> next trading-session Morning.

Current main's PR #139 code uses the IST scan date for same-day Morning/EOD comparison and research windows, while completed-session Bhavcopy/RVOL uses the latest completed session date. It also preserves strict snapshot date checks. These changes are covered by tests, but a live run on the merged PR #139 code is still needed.

### Live schedule verification

The latest available examples were manual dispatches:
- Run #332 Morning: manual, not the scheduled 09:20 execution.
- Run #335 EOD: manual at approximately 13:07 IST, before market close; not the scheduled 17:00 execution.

Therefore the schedule expressions are correct in the active YAML, but actual scheduled timing and a post-PR-#139 full comparison cycle remain operationally unverified.

## 3. Measured live-data baseline — Run #335 (pre-PR #139)

Run URL: https://github.com/digitalmf78-pixel/AI-Trading-Bot/actions/runs/43824862299

- Run #335 succeeded in approximately 2 minutes 35 seconds and delivered four Telegram parts successfully.
- It processed 25 raw NSE page rows; 23 were eligible Main Board equities after ETF/fund exclusions.
- The artifact's EOD data date was 13-Nov-2026 because the manual run happened before the 16-Nov cash-market close.
- Page `PageVolume` was missing for 23/23 eligible stocks. Turnover and page Series were also absent in the raw artifact. One-week and two-week average volume and volume-change percentages were present for 23/23.
- Fundamentals: 20/23 stocks had all seven metric values populated; 3/23 were partial. The metric-verification summary contained 17 officially verified metric observations, 25 provider-value mismatch observations, and the overall assessment was 0 PASS, 0 FAIL and 23 WAIT_FOR_DATA.
- News: 19 candidates had data; 4 had no matched news.
- Upcoming events: 7 event rows.
- Bulk/block deals: 17 deal-side rows across 3 symbols.
- Dedicated corporate-actions feed: 0 rows; a separate corporate-action-style announcement was found in the news/disclosure feed.
- Filing metadata: 16 symbols had a matched filing-metadata summary; 7 had missing filing URLs. The detailed metadata audit contained 29 explicit metadata captures and 7 incomplete rows. Remarks were extracted for 3 rows, empty for 26 and unavailable for 7. Metadata capture is not the same as metric verification.
- Fundamental source compilation contained 339 observations: 158 NSE official-XBRL audit rows, 156 Yahoo Finance observations, 23 separate NSE Debt/Equity audit rows and 2 Moneycontrol observations. The secondary-source comparison did not provide broad independent coverage across the 23-stock cohort.
- Ratio XBRL discovery contained 41 rows: 14 candidate-fact discovery rows, 20 no-candidate-fact rows and 7 no-eligible-filing-period rows. Discovery is not metric verification.
- The artifact contained 75 XBRL XML files across separate audit cache directories; 60 unique file hashes were present, with 15 duplicate XML contents between the main metric verifier and the Debt/Equity audit.

**Interpretation:** Values being populated is not the same as values being verified. The fundamental blocker is largely provenance, filing metadata, formula/context reconciliation and source coverage—not simply an absence of numeric values.

Run #335 predates PR #139. In particular, its event rows dated 13–14 November were evaluated against the older completed-data date, not the 16-Nov scan date. PR #139 changed the active code to anchor event/news/deal research to the scan date. That fix is merged and CI-tested, but the corrected live output has not yet been inspected.

## 4. High-priority code and data findings

### A. Shared cache isolation needs correction

- `strategies/ecms/eod.py:203-224` calls the shared `main_board_filter.load_official_board_lists()`.
- `main_board_filter.py:52-84` writes the live Main Board and SME CSV responses and fetched timestamps under shared `data/cache/universe/`.
- ECMS documentation declares shared production inputs/caches read-only.

This is a real isolation-contract mismatch. Before adding more data sources, route ECMS's official Main Board/SME cache to an ECMS-owned directory, without changing the default behaviour used by production NSE V8.

### B. Fundamental coverage report can misattribute the value source

In `strategies/ecms/volume_gainers.py`, the per-stock/per-metric coverage output takes `MetricSource`, `FinancialPeriodEnd` and `CalculationBasis` from the official audit/top-level row. The actual value source and period are held separately in metric-level JSON maps and in `fundamental_source_compilation.csv`.

The current coverage report can therefore display an NSE audit source beside a provider value without clearly distinguishing:
- where the displayed metric value came from;
- which official filing/XBRL source was checked;
- the value's own financial period and calculation basis;
- the official verification result and reason.

**Required correction:** publish separate `ValueSource`, `ValueSourceURL`, `ValuePeriodEnd`, `ValueBasis`, `ValueUnit`, `OfficialFilingSource`, `OfficialVerificationStatus` and `VerificationReason` fields. Resolve period/basis per metric, not from one stock-level field.

### C. Secondary fundamental research is constrained by a seven-day cooldown

The workflow sets `FREE_FUNDAMENTAL_RETRY_DAYS=7`; the provider also applies per-symbol retry/cooldown logic. The 23-candidate Run #335 summary showed only one free-source attempt, and the source compilation had only two Moneycontrol observations.

The free-source budget being large enough for 25 symbols does not mean all 25 are independently rechecked on each scan. Complete/cooldown rows can skip secondary collection.

**Required correction:** separate periodic secondary-source research from the fundamental provider's missing-data retry mechanism. Preserve cooldown for expensive fundamental refetches, but give the independent comparison/research collector its own refresh policy and coverage ledger. Do not overwrite the primary metric or upgrade third-party data to official verification.

### D. Shareholding source exists but is not active in the current ECMS scan

- `nse_shareholding.py` parses official NSE SHP XBRL for promoter, public, FII and DII percentages.
- It currently fetches the latest filing with a seven-day index cache; it does not provide an ECMS-owned multi-quarter trend series.
- Pledge is explicitly marked `NOT_MAPPED_FROM_CURRENT_NSE_FACT_CONTRACT`.
- The ECMS free-source wrapper can call this source, but the active ECMS request passes only the seven fundamental metric names. The shareholding metric family is therefore not requested by the current Volume Gainers assessment.

**Required research:** build a separate stock-level quarterly ownership history with filing period, publication date, original/revised identity and exact XBRL evidence. Investigate promoter pledge from a separately verified official disclosure source. Do not infer pledge from missing SHP facts.

### E. News and corporate-action freshness needs a Morning/EOD policy

- `collect_catalysts()` fetches official and secondary news per symbol, serially, and caches a complete exact five-session window. A complete Morning cache entry is reused by EOD for the same date window.
- This is efficient, but it can miss new disclosures published between Morning and EOD unless an incremental/delta refresh is added.
- `collect_corporate_actions()` caches raw rows by exact date window but does not store a fetched-at timestamp or explicit source-coverage metadata in the cache payload. The same window can therefore be reused without checking for newly published items.
- Events and bulk/block deals are currently batch requests for the whole candidate cohort and are fetched again at each scan.

**Required correction:** preserve the Morning snapshot, but at EOD perform a bounded incremental refresh from the Morning capture timestamp (or a verified last-seen disclosure cursor). Deduplicate by official disclosure identity and retain both Morning and EOD source timestamps. Give corporate-action caches a fetched-at/TTL or incremental refresh rule.

### F. Several data fetches are per-symbol and serial

Current per-symbol work includes:
- official NSE announcements and secondary news in `strategies/ecms/eod.py:277-440`;
- NSE integrated filing metadata in `strategies/ecms/filing_metadata_audit.py:254-382`;
- Details/Remarks HTML retrieval for each filing in `filing_metadata_audit.py:78-225`;
- shareholding XBRL lookup when requested.

Events, bulk/block deals and corporate actions are already page-cohort/batch requests in `strategies/ecms/information.py`.

**Required research:** test whether official endpoints support safe cohort retrieval, reuse one bounded session per source, cache exact filing variants, and measure request count, latency, rate limits and coverage before choosing concurrency. Do not add unbounded parallel requests.

### G. Volume data is still a key gap

Run #335 had no page volume for 23/23 candidates and no turnover in the artifact. PR #139 added raw payload-key and volume-like-field diagnostics plus more quantity aliases and tests. Those diagnostics must now be checked in a post-merge live artifact before selecting a replacement volume source.

The current `attach_page_rvol()` uses 20 prior completed Bhavcopy sessions for RVOL. It does not yet attach 5/10/20/30-session delivery quantity, delivery percentage or delivered value to the active candidate report.

### H. Institutional, trap and technical layers are not yet implemented

The active Volume Gainers path currently has:
- 20-session completed-day RVOL;
- five-session announcements/news;
- 90-day event/board-meeting lookup;
- 30-calendar-day bulk/block deals;
- corporate-action feed/disclosure view;
- seven-metric fundamental assessment and XBRL diagnostics.

It does not yet have:
- historical delivery/volume-price accumulation analysis;
- multi-quarter stock-specific institutional ownership changes;
- promoter pledge trend;
- insider/PIT/SAST transaction research as a structured stock-level evidence family;
- official ASM/GSM/ESM/T2T/PCA/price-band surveillance status;
- operator/trap risk assessment and exclusion ledger;
- sector/Nifty relative strength, breakout/retest, wick/closing-quality or entry-readiness logic.

### I. Fundamental research score implementation/documentation is inconsistent

`strategies/ecms/fundamental_research.py` exists and has tests, but the active `strategies/ecms/volume_gainers.py` imports the strict fundamental shortlist and does not import/call `assess_fundamental_research`. The current `EODResearchStatus` and Morning fundamental labels are based on the fundamental shortlist status.

The longer `docs/ECMS_VOLUME_GAINERS_README.md` describes an independent STRONG score and combined PASS + STRONG confirmation. That should not be assumed to be active. Decide whether to reuse, adapt or retire this module only after auditing its formulas and period/provenance rules.

### J. CI and documentation drift

- The active validation command runs 121 tests successfully on PR #139, but omits `tests/test_ecms_gemini_research.py` and `tests/test_ecms_secondary_source_periods.py`.
- `strategies/ecms/WORKFLOW_CONTRACT.md` says EOD is 16:45 IST; the active workflow and `strategies/ecms/README.md` say 17:00 IST.
- The README and workflow contract still declare the fundamental-only gate and say no non-fundamental field may reject. This conflicts with the user's newly approved high-trap-risk exclusion.
- `docs/ECMS_VOLUME_GAINERS_README.md` contains older research/confirmation rules and says combined fundamental PASS + STRONG is active, while current code does not call the independent fundamental research scorer.
- The legacy manual-only workflow remains labelled DO NOT USE. It is not scheduled but should remain clearly separated from the active two-scan workflow.

## 5. Audit priority and proposed implementation order

| Priority | Work | Why it comes first |
|---|---|---|
| P0 | Lock comparison regression tests; correct ECMS Main Board cache isolation; reconcile schedule/docs | Protect existing workflow and production boundary |
| P1 | Build field/source dictionary and per-stock/per-metric provenance-correct report | Avoid making decisions from misleading or unverified data |
| P2 | Repair volume, turnover, liquidity and 5/10/20/30-session delivery history | Establish actual accumulation and abnormal-volume evidence |
| P3 | Activate official shareholding history; research promoter pledge and insider disclosures | Add stock-specific institutional evidence |
| P4 | Improve announcement/news/event/deal/action completeness and Morning-to-EOD incremental refresh | Ensure research is current and traceable |
| P5 | Add official surveillance status and multi-signal trap research, first in shadow mode | Define evidence-based exclusion without false accusations |
| P6 | Add sector-relative strength and technical entry-readiness history | Separate research quality from actionable setup |
| P7 | Define balanced decision model and high-trap exclusion only after historical false-positive review | Avoid opaque or premature scoring |
| P8 | Shadow validation, forward-outcome testing, runtime and live scheduled cycle | Prove behaviour before enabling new rules |

## 6. User-approved policy to apply after audit

- Balanced quality assessment: fundamentals + verified footprint + low trap risk + technical readiness.
- High trap risk is excluded from the normal shortlist; preserve a separate exclusion ledger with evidence and reason.
- One isolated weak signal is not sufficient for `TRAP_RISK_HIGH`.
- `NOT_VERIFIED`, `SOURCE_UNAVAILABLE` and missing data are not proof of a trap and do not become low risk.
- Fundamental FAIL is never overridden by footprint. Fundamental WAIT remains WAIT.
- Morning/EOD comparison, schedule, cache handoff, date logic and repeat labels stay unchanged.
- Production NSE V8 and unrelated workflows stay untouched.

## 7. Immediate next step

Use this audit to revise `ECMS_RESEARCH_ROADMAP_AUDIT_FIRST.md`. Start implementation only with P0 and P1 on this isolated branch, one small PR at a time. Before coding P2-P6, complete source-contract research and collect representative historical samples to prove coverage and correctness.
