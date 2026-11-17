# ECMS — NSE Volume Gainers Fundamental Research

**Purpose:** ECMS researches every eligible NSE Main Board stock present in each NSE Volume Gainers page snapshot. PASS, FAIL and WAIT_FOR_DATA are assessment outcomes only: none may prevent a stock from receiving news, events, deals or other research. No rejection/hand-off filter is to be added until the complete research output and source quality have been reviewed.

This file is the source of truth for ECMS scope, rules, roadmap and hand-off. Read it before changing ECMS code or interpreting ECMS reports.

- Workflow: .github/workflows/ecms-volume-gainers-shadow.yml
- Scanner: strategies/ecms/volume_gainers.py
- ECMS free-source adapter: strategies/ecms/free_fundamental_sources.py
- Fundamental scoring: strategies/ecms/fundamental_research.py
- Isolated cache/state: data/cache/ecms/
- Reports: outputs/ecms/

---

## 1. Non-negotiable scope

1. **Only NSE Volume Gainers page stocks.** Use the current page response for that run. Never scan the full NSE Mainboard universe, another watchlist, a separate batch, or any unrelated stock list.
2. **Assess every eligible row returned by the page.** The page currently labels its table Top 25, but process every valid row returned; do not hard-code exactly 25 if NSE returns a different count.
3. Match symbols against the official NSE Main Board equity list. Exclude SME/ETF/MF/non-equity entries and retain the exclusion reason.
4. Fundamentals are mandatory for the ECMS hand-off. Missing, stale, conflicting or unproven fundamentals must remain WAIT_FOR_DATA / not qualified; never call them strong.
5. Do not import V8 Delivery A/B, V8 liquidity, V8 technical filters, V8 hybrid watchlists or V8 candidate lists into ECMS.
6. Do not mix ECMS with IPO V8 or any other project.
7. ECMS is research-only. It must never place orders or issue automatic buy instructions.
8. Keep ECMS cache, state, diagnostics and reports isolated under data/cache/ecms/ and outputs/ecms/. Shared production inputs may be read as seed data only; never mutate the production fundamental cache or production reports.
9. Do not modify .github/workflows/nse-test-scheduled.yml for ECMS work.
10. Free/open-source sources only. No paid API, subscription, secret API key or mandatory AI provider.

## 2. ECMS run flow

### EOD research

1. Fetch the NSE Volume Gainers page and its page-data endpoint.
2. Preserve raw page rows and normalize symbol/company/series, page volume, LTP, percentage change, turnover and available one-/two-week volume fields.
3. Apply official NSE Main Board equity eligibility.
4. Resolve the latest completed NSE cash-market session and tag the run with that EOD date. Weekends/holidays must resolve to the latest completed session.
5. Attach 20-session RVOL as context only. Missing RVOL is WAIT_FOR_DATA but does not remove a Volume Gainer candidate.
6. Collect or safely reuse fundamental data for every current eligible page candidate.
7. Run official-filing/XBRL verification for those same candidate symbols. Keep official verification separate from third-party research data.
8. Produce strict fundamental shortlist status and independent fundamental research score/classification.
9. Collect five official NSE trading sessions of announcements/news for every eligible candidate; reuse only complete, date-matched cached source results.
10. Collect the next 90 calendar days of NSE event-calendar and board-meeting entries for every eligible candidate; expose the next confirmed financial-results date separately.
11. Collect 30 calendar days of bulk and block deals for every eligible candidate, with a separate recent five-calendar-day count/summary. Normalize both current NSE CSV fields and documented BD-prefixed deal fields; preserve source-unavailable status separately from a checked empty result.
12. Preserve corporate-action announcements found in the official five-session disclosure/news window. Do not claim a dedicated historical/upcoming corporate-actions feed until its official source and parser are independently validated.
13. Produce one final EOD research row per eligible candidate plus source-wise statuses and raw/provider/filing/verification/news/event/deal diagnostics. Provider failure must not silently drop a candidate.
14. Save the EOD candidate snapshot for the morning comparison.

### Scan-date vs completed-data-date contract

- Every Morning or EOD run records its IST **ScanDate** and exact capture timestamp separately from **DataAsOfDate** (the latest completed official NSE session).
- Same-day Morning-to-EOD membership comparison uses ScanDate only. A manual EOD-mode run on the same trading date must compare with that date's valid Morning snapshot even if it runs before market close and the latest completed Bhavcopy date is the prior session.
- Completed-session indicators such as 20-session RVOL must retain their DataAsOfDate. Morning RVOL is reported only as prior-completed-session context; it must never be described as a live partial-session RVOL.
- The Morning snapshot date guard remains strict: wrong-date, duplicate-symbol, invalid-type or invalid-status snapshots are rejected.

### 09:20 IST morning recheck and second fundamental assessment

1. Load the previous valid EOD Volume Gainers snapshot **and its per-symbol fundamental assessment** from ECMS state.
2. Confirm its EOD date matches the latest completed NSE session.
3. Fetch the current NSE Volume Gainers page and apply the same official Main Board eligibility rule.
4. Compare membership: prior EOD symbols are REPEATED or DISAPPEARED; current symbols absent from the prior EOD snapshot are NEW_ENTRY.
5. **Run the same fundamental assessment framework on every eligible company on the current 09:20 page**, including both REPEATED and NEW_ENTRY companies. Keep strict shortlist status and independent research score/classification separate.
6. Reuse fresh, complete, provenance-bearing ECMS fundamental data where valid. Reassess it against the morning candidate; attempt missing/incomplete data under ECMS retry rules and keep unresolved cases WAIT_FOR_DATA. Do not treat cache presence or a prior EOD STRONG label as a morning pass.
7. Save morning fundamental results alongside the membership comparison and preserve the original EOD assessment for direct comparison.
8. Apply the confirmation labels below. A company must independently satisfy strict shortlist PASS and research STRONG at both checkpoints to receive DOUBLE_CONFIRMED.

### EOD + Morning confirmation labels

- `STRONG_EOD`: the EOD assessment has strict shortlist PASS and independent research classification STRONG with required coverage/provenance.
- `UNDER_OBSERVATION_MORNING`: the company appears on the 09:20 Volume Gainers page and its morning assessment is independently STRONG + strict PASS, but it did not qualify as STRONG at EOD (for example, it is a NEW_ENTRY).
- `DOUBLE_CONFIRMED_EOD_MORNING`: the same symbol was present and qualified as STRONG + strict PASS in the EOD assessment, appears again on the 09:20 page, and independently qualifies as STRONG + strict PASS in the morning assessment.
- Keep EOD-only, morning-only and double-confirmed labels distinct. Do not collapse a repeated symbol into an undifferentiated duplicate or overwrite its EOD record.
- If the symbol is present in both runs but either checkpoint is not STRONG + strict PASS, it is **not** DOUBLE_CONFIRMED. Show the two checkpoint results and the reason (FAIL, WAIT_FOR_DATA, incomplete provenance, or non-STRONG classification).
- A disappeared EOD candidate retains its EOD record but cannot be double-confirmed for that morning.
- DOUBLE_CONFIRMED is a research-priority/consistency label, not a buy signal or trade instruction.

## 3. Fundamental data to collect

For every eligible current-page candidate, collect or reuse dated, attributable data where available.

### Financial statements and operating performance
- Annual and quarterly income statement, balance sheet and cash-flow statement.
- Revenue and revenue growth; net profit and profit growth; EPS.
- Gross, operating and net profit margins.
- ROE and ROCE.
- Operating cash flow and free cash flow.
- Debt/equity and interest coverage.
- Current ratio, quick ratio and asset turnover where meaningful.

### Ownership and capital structure
- Promoter holding and promoter pledge.
- FII, DII and public holding.
- Shareholding reporting period and source filing.

### Valuation snapshot
- Price and valuation as-of date.
- Market capitalization / enterprise value where available.
- Trailing P/E, forward P/E, P/B, EV/EBITDA, P/S, P/FCF and PEG where available.
- Dividend yield where available.
- Every valuation snapshot needs its source and as-of date. Never present stale valuation as current.

### Company context
- Sector/industry classification.
- Company announcements and material corporate actions.
- Recent candidate-specific news/catalysts and negative-risk evidence.
- Source URL, retrieval time, reported financial period and provider diagnostics.

Missing fields must remain explicitly missing. Never manufacture, estimate or silently fill financial values.

## 4. Source hierarchy and verification

1. Official NSE Integrated Filing / XBRL is the primary source for official verification.
2. Yahoo Finance via yfinance is secondary provider evidence, not an official filing.
3. Moneycontrol and Tickertape are third-party provider evidence collected through the open-source Bharat-sm-data client. Public website endpoints are not official supported APIs and may change, rate-limit or block automated access. Respect source terms.
4. A provider value is never OFFICIAL_XBRL_VERIFIED merely because it was downloaded, has a URL or agrees with another provider.
5. Official verification requires the existing fail-closed filing audit: filing source, issuer identity, XBRL context, period, unit/value and evidence integrity must pass.
6. Record provenance per metric: source name, source URL, reporting period, calculation basis and currency where applicable.
7. Yahoo metrics may enter independent research scoring only when aligned annual/quarterly statement basis and MetricPeriodAlignmentStatus=VERIFIED rules pass.
8. Non-Yahoo metrics may enter scoring only with metric-level source/period provenance and MULTI_SOURCE_METRIC_LEVEL basis. They remain third-party evidence.
9. Third-party growth values require an explicit consecutive fiscal-year pair, e.g. FY2024->FY2025. A single year label is insufficient.
10. Reject stale periods older than the 24-month rule and future periods beyond the 31-day tolerance. Preserve the reason.
11. MetricPeriodAlignmentStatus=VERIFIED is provider statement-period alignment, not official exchange verification.
12. Do not infer promoter pledge from ordinary promoter holding. Pledge remains unavailable until an exact validated official fact mapping exists.
13. Keep the actual metric-specific source URL. Never substitute a generic provider homepage when the actual URL is unavailable.

## 5. Fundamental decision and hand-off rules

ECMS must show two independent assessments. They answer different questions and must not be merged.

### A. Strict fundamental shortlist
Use the existing fundamental_shortlist.py logic and explicit configured thresholds. Do not weaken thresholds to make more stocks pass. Preserve PASS, FAIL and WAIT_FOR_DATA. PASS is not an automatic buy recommendation.

### B. Independent Fundamental Research Score
Use strategies/ecms/fundamental_research.py with metric-level provenance and period gates. Preserve:
- Numeric score only when minimum evidence coverage is met.
- Coverage percentage.
- STRONG, GOOD, AVERAGE, WEAK or INSUFFICIENT_DATA classification.
- Eligible metric count and provenance status.
- Separate official verification status and verified metric count.
- Explicit missing-input and provenance-blocked reasons.

Current generic score bands:
- STRONG: coverage at least 80% and score at least 75.
- GOOD: coverage at least 65% and score at least 60, but not STRONG.
- AVERAGE: score at least 45 when higher classifications do not apply.
- WEAK: score below 45 when sufficient coverage exists.
- INSUFFICIENT_DATA: coverage below 60% or no publishable score.

**Sector exception:** Banks, NBFCs and insurers must not be judged with generic industrial debt/equity and ROCE thresholds. Keep them INSUFFICIENT_DATA until a separate validated sector model exists, with suitable measures such as NIM, GNPA/NNPA and capital adequacy (CAR), as applicable.

### C. Research-first policy — current approved behavior

- Every eligible page stock receives the same research collection attempt regardless of strict shortlist PASS, FAIL or WAIT_FOR_DATA.
- Fundamental classifications remain visible as one independent research dimension; they do not control whether news, announcements, events, bulk/block deals or corporate-action disclosures are collected.
- Do not drop, suppress or hide FAIL/WAIT stocks from the complete research report. Missing sources remain explicitly unavailable/unverified, not negative evidence.
- No STRONG_FUNDAMENTAL hand-off, rejection filter or final selection gate is authorized in this phase. Add such a stage only after the user reviews complete data coverage and explicitly approves the rules.
- Positive catalyst/news cannot repair weak or missing fundamentals. Negative-risk evidence must remain visible.

**Implementation note:** Current scanner code runs strict shortlist and research scoring as separate columns. The final hand-off must explicitly enforce the combined rule above. Strict shortlist PASS alone does not prove independent research classification STRONG.

## 6. Cache, retry and completeness contract

- ECMS fundamental workspace is separate from the shared V8 cache.
- Fresh, complete, provenance-bearing cached data may be reused; do not re-fetch complete statements without a reason.
- Every current candidate must still receive a fresh assessment row for this run, even when data is reused.
- Missing, incomplete, stale or provenance-blocked fields must remain visible. Cache presence alone is not proof of completeness.
- Provider cooldowns are efficiency controls, not permission to mark missing data complete.
- If required data is missing and retry is deferred, record RETRY_COOLDOWN plus missing fields and keep the candidate WAIT_FOR_DATA / not forwarded.
- Free-source budget must cover the full current page cohort. If the page returns more than the budget, report unattempted candidates and do not claim full collection.
- News cache entries are reusable only for the exact symbol and exact five-session date window, and only after both official and secondary source attempts completed. Failed/partial attempts are retried; Morning's complete same-day results can be reused by EOD to avoid duplicate requests.
- Event-calendar, bulk/block-deal and corporate-actions APIs are batch requests for the whole page cohort, not one request per stock. Keep the 30-day deal detail and five-day deal summary side by side. Corporate-actions responses are cached by exact date window.
- Provider errors must not delete candidates or overwrite valid prior/manual values.
- Duplicate symbol rows in the fundamental cache are an integrity error; never arbitrarily choose one.
- Final report must have exactly one assessment row per eligible candidate symbol. A mismatch in count or symbol set is a run-integrity failure.

## 7. Required reports

| Artifact | Purpose |
|---|---|
| volume_gainers_page_raw.csv | Raw normalized NSE page rows before Main Board filtering, including original NSE payload keys and volume-field diagnostics |
| volume_gainers_eod_research.csv | One joined fundamental/research/catalyst assessment per eligible candidate |
| volume_gainers_catalysts.csv | Five-NSE-session candidate-specific announcement/news evidence for every eligible stock |
| volume_gainers_upcoming_events.csv | Next-90-calendar-day official event-calendar rows for every eligible stock |
| volume_gainers_bulk_block_deals.csv | 30-calendar-day official deal detail for every eligible stock, including five-day summary fields |
| volume_gainers_corporate_actions.csv | Official NSE corporate actions by ex-date across the previous five-session start date through the next 90 calendar days |
| volume_gainers_eod_summary.json | Run date, page count, eligible count, assessed count, strong count and wait count |
| fundamental_metrics_ecms.csv | ECMS-owned fundamental cache snapshot |
| fundamental_provider_diagnostics.csv | Provider attempts, cache/retry status and missing-data details |
| fundamental_filings_ecms.csv | ECMS-owned filing metadata |
| fundamental_evidence_ecms.csv | ECMS-owned evidence ledger |
| fundamental_metric_verification_summary.csv | Official metric verification summary |
| fundamental_filing_metadata_summary.csv | Filing metadata verification summary |

The exact artifact bundle may include additional XBRL evidence/diagnostic files. Keep raw/provider/official evidence separate from final classification.

Required summary counts: page rows; eligible Main Board candidates; assessment rows/unique symbols; strong hand-off count; good/average/weak counts; FAIL count; WAIT_FOR_DATA/insufficient/provenance-blocked count; provider attempted/cache reused/cooldown-deferred/failed counts; duplicate/missing assessment integrity count.

## 8. Research collection windows and status meanings

- Announcements/news: previous five official NSE trading sessions, inclusive of the as-of session.
- Upcoming events and board meetings: next 90 calendar days from the scan as-of date. Keep each feed's source status visible; a checked empty calendar is not the same as a failed feed.
- Bulk and block deals: previous 30 calendar days; also expose separate five-calendar-day counts and summaries. Keep the disclosed buyer/seller side, client, date, quantity and price when the source provides them.
- Corporate actions: include official corporate-action announcements appearing in the five-session disclosure window. A dedicated corporate-actions endpoint remains NOT_VERIFIED until validated against official NSE data; do not infer an empty result from an unavailable source.
- Each research family must distinguish `DATA_FOUND`, `NO_DATA_FOUND`, `SOURCE_UNAVAILABLE` and `NOT_VERIFIED`. `NO_DATA_FOUND` is valid only when the source was successfully queried for the requested window.
- Performance: use page-wide batch APIs where available, exact-window persistent cache reuse for complete news results, and existing fundamental cache/cooldown controls. Never cache a failed or partial fetch as a successful empty result.

## 9. Roadmap and current status

Statuses reflect code inspected on 15-Nov-2026. They are not claims that a live market run has succeeded.

| Phase | Scope | Status |
|---|---|---|
| 0 | Isolated ECMS workflow/cache, no V8 production workflow changes | Implemented |
| 1 | NSE Volume Gainers fetch/normalization and official Main Board eligibility | Implemented |
| 2 | EOD session date, page RVOL context, raw page snapshot and candidate state | Implemented |
| 3 | Free-source fundamental collection, metric-level provenance and source URLs | Implemented; provider availability varies |
| 4 | Official filing/XBRL verification, strict shortlist and separate research scoring | Implemented; data coverage may be incomplete |
| 5 | Per-candidate completeness guarantee, ECMS opt-in retry for incomplete rows, complete-cache reuse and one-row-per-candidate assertion | Implemented in code; automated validation pending |
| 6 | Combined strict-PASS + independent-STRONG (coverage >=80%) hand-off and explicit not-forwarded reasons | Implemented in code; automated validation pending |
| 7 | Candidate-specific catalyst/news and negative-risk review | Implemented; source coverage varies |
| 8 | 09:20 IST membership comparison plus same-framework fundamental reassessment and EOD/Morning confirmation labels | Implemented in code; live schedule/run verification pending |
| 9 | End-to-end EOD and morning artifact audit on actual runs | Pending operational sign-off |

### Completion checklist — ECMS is final only when all pass

- [ ] Only current NSE Volume Gainers eligible Main Board candidates are processed.
- [ ] Every candidate has exactly one assessment row for that run.
- [ ] Fresh complete data is safely reused; missing/incomplete data is attempted or explicitly marked deferred/failed.
- [ ] Provider cooldown cannot make missing data look complete or strong.
- [ ] Strict shortlist and independent research classification remain separate.
- [ ] Only strict PASS + independent STRONG candidates enter strong-fundamental hand-off.
- [ ] Bank/NBFC/insurance generic scoring remains blocked until the sector model exists.
- [ ] Every scored metric has valid metric-level provenance and period; stale/future/invalid evidence is blocked.
- [ ] Official XBRL verification remains fail-closed and is never inferred from provider data.
- [ ] Reports include every candidate and explain every non-forwarded result.
- [ ] Morning comparison correctly reports REPEATED / DISAPPEARED / NEW_ENTRY.
- [ ] Every eligible 09:20 candidate receives the same fundamental assessment framework as EOD (with safe complete-cache reuse).
- [ ] EOD-only, morning under-observation and DOUBLE_CONFIRMED_EOD_MORNING labels are independently recorded; double confirmation requires strict PASS + STRONG at both checkpoints.
- [ ] ECMS validation tests pass and V8 regression tests pass.
- [ ] .github/workflows/nse-test-scheduled.yml is unchanged.
- [ ] A real EOD run and a real morning run each produce audited artifacts before operational success is claimed.

## 9. Engineering and change-control rules

- Work only on ECMS files or an explicitly reviewed opt-in shared-module change.
- Shared-module changes must default to existing V8 behavior and include regression tests proving V8 is unchanged.
- Never edit the V8 production workflow for ECMS.
- No paid dependencies, API keys, Gemini calls or mandatory external AI steps.
- Add offline tests for every parser, identity rule, retry path, missing-data case and shortlist gate.
- Validate on a PR first. PR validation is not a live EOD or morning market run; those jobs are skipped on PR events by design.
- Merge only after all required checks pass, using the exact tested PR head SHA.
- After merge, verify Main and confirm the V8 production workflow did not change.
- Do not claim full completion from unit tests alone. Inspect actual EOD/morning artifacts and counts.
- Never create a forced shortlist. WAIT_FOR_DATA is a valid outcome.

## 10. Next ECMS-only implementation tasks

The ECMS scanner now opts into retrying incomplete candidate data without changing the shared collector's default behavior, preserves complete-cache reuse, asserts exact candidate-to-assessment row integrity, and exposes a strict PASS + independent STRONG (coverage >=80%) hand-off gate. The 09:20 job now runs the same fundamental assessment for every eligible current-page candidate and compares its result with the preserved EOD assessment.

Remaining ECMS-only work:

1. Validate the opt-in retry behavior, complete-cache reuse, all-candidate row preservation, strict-PASS-but-not-STRONG rejection and true STRONG acceptance in CI.
2. Verify the 09:20 report emits distinct EOD, morning-under-observation and DOUBLE_CONFIRMED_EOD_MORNING statuses; the latter requires strict PASS + STRONG at both checkpoints.
3. Review provider diagnostics to ensure every missing metric, provider attempt/defer/error and cache reuse is visible per candidate.
4. Run ECMS EOD manually for an end-to-end artifact audit; run morning mode separately on a valid trading day with valid prior state.
5. Confirm actual morning artifacts contain every eligible current-page candidate's fundamental assessment and accurate EOD/Morning confirmation counts.

The code changes remain ECMS-only; the V8 production workflow and its default collector behavior are not changed.

**Do not broaden ECMS work beyond these requirements.**


## Manual dispatch mode — session-close rule (17-Nov-2026)

- Every manual `workflow_dispatch` starts through one automatic EOD resolver; users do not choose EOD or Morning in the GitHub form.
- On an official NSE trading session, a manual run at or after 15:30 IST resolves to EOD. A manual dispatch before 15:30 IST is explicitly SKIPPED as `MANUAL_RUN_BEFORE_NSE_CLOSE`; it is not silently converted into a Morning scan.
- The resolver uses IST wall-clock time. The official NSE trading calendar still blocks holidays and unavailable calendar coverage. Scheduled Morning/EOD jobs retain their explicit schedule-specific modes and slot validation.
- The previous EOD CSV remains eligible as the Morning reference only when its snapshot metadata, session date, completeness and consumption state pass the existing validation. A CSV artifact alone is not sufficient proof of a valid persisted EOD snapshot.
- ECMS state cache uses a new versioned namespace and NSE-session-date prefixes. Morning restores only the cache partition for the exact latest completed NSE session; EOD prefers the current session's Morning partition, then the immediately preceding completed session. Older unscoped cache keys are deliberately excluded. The independent fundamental cache remains restored separately.


### EOD snapshot validation — 16-Nov-2026

- Verified manual EOD run [43866492965](https://github.com/digitalmf78-pixel/AI-Trading-Bot/actions/runs/43866492965): EOD job SUCCESS; the Morning job was correctly skipped for this EOD dispatch.
- The run reported `ECMS_EOD_SNAPSHOT_CACHEABLE=True` and saved the ECMS state cache. Telegram delivered all four report parts (message IDs 2303–2306) and the full NSE page CSV (message ID 2307; 14,324 bytes).
- Artifact `ecms-volume-gainers-eod-43866492965` (ID 14226655517) was inspected: `volume_gainers_eod_nse_page.csv` contains 25 rows, 22 official Main Board eligible; every row has `ScanMode=EOD` and `ScanDateIST=2026-11-16`. Summary dates are ScanDate 16-Nov, DataAsOfDate 16-Nov and EOD date 16-Nov.
- The following Morning run #433 (run ID 44018285950) failed closed because cache restore selected a later 17-Nov snapshot instead of the required 16-Nov EOD reference. A later cancelled pre-close manual EOD run #427 had also written a same-prefix state cache, illustrating why date-unscoped restore keys were unsafe.
- The 17-Nov fix therefore introduces a new `ecms-vg-state-v2` namespace, saves state by NSE scan-session date plus run ID, and restores Morning state only from the exact latest completed NSE session date. Legacy unscoped state caches are not eligible for v2 restores.


## One-click ECMS scan routing (IST)

ECMS has one workflow-dispatch button and no user-selected EOD/Morning input. A small routing job selects the internal scan job from the current IST time for manual dispatches; scheduled events are routed by their configured cron slot. The scanner jobs remain internally separated so their snapshot/cache validation and Telegram reports stay mode-specific.

| IST window | Manual dispatch route | Behaviour |
|---|---|---|
| 15:30–23:59 | EOD | Run the completed regular-session EOD scan |
| 00:00–07:59 | EOD REUSE | Reuse the latest validated EOD snapshot; do not fetch/refresh live NSE data |
| 08:00–09:14 | SKIP | EOD reference is locked; no fresh EOD or Morning scan |
| 09:15–11:59 | Morning | Double-confirm latest EOD candidates and observe new stocks |
| 12:00–15:29 | SKIP | Avoid incomplete intraday data |

Scheduled routing remains at 17:01 IST for EOD and 09:21 IST for Morning. The official NSE trading calendar and each mode's existing data-date checks remain authoritative; a weekday schedule on a holiday must not create a scan. A skipped manual dispatch writes its routing decision to the Actions step summary and sends a short Telegram notice when Telegram secrets are configured.

EOD is the primary selection and entry-trigger engine. Morning is confirmation/observation only: it must not overwrite the EOD entry trigger or convert a new observation into an EOD entry signal. The 00:00–07:59 IST window is snapshot reuse only; it must not refresh live NSE data. The 08:00 IST lock closes EOD reuse until Morning opens at 09:15.
