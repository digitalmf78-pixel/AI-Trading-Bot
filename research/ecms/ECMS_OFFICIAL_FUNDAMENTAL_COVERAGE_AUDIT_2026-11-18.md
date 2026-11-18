# ECMS Official Fundamental Coverage Audit — 18 November 2026

## Status and evidence boundary

**Research-only audit. No production code, thresholds, workflows, caches or NSE V8 files were changed.**

- Repository baseline: `main` at `6144f5c9c197ffa1c301f2ac9b9a7f5450a21a7a`.
- Audit branch: `research/ecms-official-fundamental-coverage-2026-11-18`.
- Latest complete ECMS EOD cohort available for inspection: workflow Run #335, EOD data date **13-Nov-2026**, artifact created 16-Nov-2026.
- That artifact contains **25 raw NSE Volume Gainers page rows**; 2 ETF rows were excluded and **23 eligible Main Board equities** remained.
- A newer 18-Nov Morning dispatch (Run #541) did not produce a new cohort. It stopped with `WAIT_FOR_DATA`: cached EOD snapshot date was 16-Nov-2026 while the latest completed NSE session expected by the job was 17-Nov-2026. Therefore this report is a verified audit of the **last complete 23-stock cohort**, not a claim that these are the live 18-Nov Top-25 symbols.
- The audit uses the stored Run #335 CSV/XBRL evidence. It does **not** claim that fresh NSE/BSE requests for all 23 companies were executed on 18-Nov. A BSE fallback crawl is still outstanding.

## Executive result

| Measure | Result |
|---|---:|
| Raw NSE page rows | 25 |
| ETF rows excluded | 2 |
| Eligible Main Board shares audited | 23 |
| Shares with all 7 numeric values populated | 20 |
| Shares with partial numeric coverage | 3 |
| Seven-metric observations assessed | 161 |
| `OFFICIAL_XBRL_VERIFIED` observations in central metric report | 17 |
| Provider-vs-official mismatches | 25 |
| Derived metrics requiring component reconciliation | 64 |
| Filing metadata not confirmed | 48 |
| Provider-only observations | 4 |
| Not verified / missing observation | 3 |
| Stocks with strict fundamental PASS | 0 |
| Stocks with strict fundamental FAIL | 0 |
| Stocks retained as `WAIT_FOR_DATA` | 23 |

**Conclusion:** populated numbers are not equivalent to trustworthy verified fundamentals. The 23-stock cohort has enough data to research, but not enough consistent official verification to promote any stock as a verified fundamental PASS. Keep the current fail-closed policy. Do not switch the production fundamental gate or delete the secondary provider observations yet.

## Audited eligible cohort

All 23 symbols below were present in the last complete eligible ECMS research artifact:

| Symbol | Company | Seven-value coverage | Officially verified observations | Strict status |
|---|---|---:|---:|---|
| RPSGVENT | RPSG Ventures | 7/7 | 0 | WAIT_FOR_DATA |
| PBMPOLY | PBM Polytex | 6/7 | 0 | WAIT_FOR_DATA |
| TVSSCS | TVS Supply Chain Solutions | 6/7 | 0 | WAIT_FOR_DATA |
| MUKESHB | Mukesh Babu Financial Services | 7/7 | 0 | WAIT_FOR_DATA |
| SONAL | Sonal Mercantile | 7/7 | 0 | WAIT_FOR_DATA |
| ARYAMAN | Aryaman Financial Services | 7/7 | 0 | WAIT_FOR_DATA |
| INDRAMEDCO | Indraprastha Medical Corporation | 7/7 | 2 | WAIT_FOR_DATA |
| TVSSRICHAK | TVS Srichakra | 7/7 | 0 | WAIT_FOR_DATA |
| VIPCLOTHNG | VIP Clothing | 7/7 | 2 | WAIT_FOR_DATA |
| BELRISE | Belrise Industries | 7/7 | 0 | WAIT_FOR_DATA |
| DSSL | Dynacons Systems & Solutions | 7/7 | 2 | WAIT_FOR_DATA |
| SAPPL | Shree Ajit Pulp & Paper | 7/7 | 0 | WAIT_FOR_DATA |
| CLCIND | CLC Industries | 6/7 | 0 | WAIT_FOR_DATA |
| BOROLTD | Borosil | 7/7 | 2 | WAIT_FOR_DATA |
| KAYNES | Kaynes Technology India | 7/7 | 2 | WAIT_FOR_DATA |
| ORCHPHARMA | Orchid Pharma | 7/7 | 0 | WAIT_FOR_DATA |
| GALLANTT | Gallantt Ispat | 7/7 | 1 | WAIT_FOR_DATA |
| DEEPAKFERT | Deepak Fertilisers and Petrochemicals | 7/7 | 1 | WAIT_FOR_DATA |
| KJMCFIN | KJMC Financial Services | 7/7 | 0 | WAIT_FOR_DATA |
| HINDADH | Hindustan Adhesives | 7/7 | 0 | WAIT_FOR_DATA |
| PRICOLLTD | Pricol | 7/7 | 2 | WAIT_FOR_DATA |
| YATRA | Yatra Online | 7/7 | 2 | WAIT_FOR_DATA |
| UGROCAP | Ugro Capital | 7/7 | 1 | WAIT_FOR_DATA |

Excluded raw page rows: `IVZBANKNF` (Invesco India Nifty Bank ETF) and `LICMFGOLD` (LIC MF Gold ETF). They are not company-equity fundamental candidates.

## Seven-metric verification detail

Counts below are based on the 23 × 7 central per-stock/per-metric coverage file. `Available` means a numeric candidate value exists; it does not mean that value is verified.

| Metric | Numeric values available | Officially verified | Provider mismatch | Derived reconciliation required | Filing metadata not confirmed | Provider only | Not verified |
|---|---:|---:|---:|---:|---:|---:|---:|
| Revenue Growth | 23 | 2 | 12 | 0 | 7 | 2 | 0 |
| Profit Growth | 20 | 6 | 6 | 0 | 6 | 2 | 3 |
| ROE | 23 | 0 | 0 | 16 | 7 | 0 | 0 |
| ROCE | 23 | 0 | 0 | 16 | 7 | 0 | 0 |
| Debt/Equity | 23 | 0 in central verifier | 0 in central verifier | 16 | 7 | 0 | 0 |
| Interest Coverage | 23 | 0 | 0 | 16 | 7 | 0 | 0 |
| Operating Cash Flow | 23 | 9 | 7 | 0 | 7 | 0 | 0 |
| **Total** | **158** | **17** | **25** | **64** | **48** | **4** | **3** |

### Important reconciliation discrepancy — Debt/Equity

The separate Debt/Equity component audit has a different result from the central seven-metric coverage report:

- 1 `OFFICIAL_XBRL_VERIFIED` (GALLANTT)
- 1 `PROVIDER_VALUE_WITHIN_XBRL_ACCURACY` (CLCIND; interval acceptance, not exact equality)
- 13 `PROVIDER_VALUE_MISMATCH`
- 5 `NOT_APPLICABLE_FINANCIAL_SECTOR`
- 3 `FILING_URL_MISSING`

The central metric coverage table still labels 16 rows `DERIVED_RECONCILIATION_REQUIRED` and 7 `FILING_METADATA_NOT_CONFIRMED`. These reports are not yet harmonized. Do not silently combine the dedicated audit's one exact match into the central verified count. Fix the report contract and metric-level provenance first.

## Official filing coverage and missing metadata

The archived filing register contained filing rows for 16 of the 23 symbols. Seven symbols had no matched official filing URL / filing metadata confirmation in the captured cohort:

- ARYAMAN
- HINDADH
- KJMCFIN
- MUKESHB
- PBMPOLY
- SAPPL
- SONAL

This is a **lookup/metadata gap**, not proof that the companies did not file results. The next audit must search NSE Integrated Filing and BSE XBRL/financial results independently, match exact exchange symbol/security identity, period end, publication date, original/revised sequence, audited/unaudited label and consolidated/standalone basis, and record the actual filing URL.

The filing metadata audit captured 29 explicit metadata rows and 7 incomplete rows. Metadata capture is not itself proof that every metric was correctly verified.

## Sector-specific treatment

Provider-sector metadata marks these five cohort members as financial services:

- ARYAMAN
- MUKESHB
- SONAL
- KJMCFIN
- UGROCAP

For banks/NBFCs/financial services, the generic industrial Debt/Equity, ROCE and interest-coverage framework must not be applied blindly. Create a distinct financial-sector metric policy before assessing these companies. Confirm entity type from official issuer/exchange records rather than relying only on provider sector labels.

## Source-quality findings

1. **Revenue Growth:** only 2 of 23 observations were centrally verified. Twelve values mismatched official recomputation; two were provider-only; seven lacked filing metadata.
2. **Profit Growth:** 6 verified, 6 mismatches, 2 provider-only, 3 not verified and 6 metadata-blocked. Ensure PAT definition and annual filing basis are identical.
3. **ROE and ROCE:** no central observation was verified. Sixteen rows need component-level reconciliation and seven are metadata-blocked. Formula, average-vs-closing equity/capital employed and consolidated-vs-standalone basis must be explicit.
4. **Debt/Equity:** central and dedicated audit reports disagree; separate audit shows 13 mismatches and five financial-sector exclusions. Resolve report consistency and sector policy.
5. **Interest Coverage:** no central observation verified. Sixteen rows require EBIT/finance-cost component reconciliation and seven lack filing metadata.
6. **Operating Cash Flow:** 9 verified, 7 mismatches and 7 metadata-blocked. Preserve exact XBRL fact tag, period context, INR unit, filing identity and cash-flow cross-foot checks.
7. Yahoo Finance, Moneycontrol and Tickertape values are observations only until reconciled. Do not treat agreement between third-party providers as official verification.

## Next work, in order

### A. Rebuild the current cohort first
- Resolve the EOD → Morning snapshot mismatch that blocked Run #541.
- Obtain a successful current ECMS run and its exact raw page CSV.
- Re-run the audit on the then-current Top-25 page rows; process every returned eligible row, not a hard-coded 25.
- Keep the 13-Nov 23-stock cohort as historical baseline only.

### B. Official-source filing recovery for all current candidates
- Query NSE Integrated Filing — Financials / XBRL for every eligible symbol.
- Query BSE Integrated Filing — Financial Results / XBRL as an independent fallback and cross-check.
- Capture exact filing metadata, revisions, original/revised status, audit status, basis, period end, publication date, issuer identifier, source URL and retrieval timestamp.
- Do not infer a missing filing from a company name-only search hit. Ambiguous or mismatched issuer identity remains `WAIT_FOR_DATA`.

### C. Verify the seven metrics from source facts
- Revenue Growth and Profit Growth: independently recompute from two same-basis annual filings and document PAT/revenue line selection.
- ROE: profit numerator divided by average opening/closing equity under a declared formula.
- ROCE: EBIT numerator divided by explicitly defined capital employed; define financial-sector exclusions.
- Debt/Equity: borrowings and equity components from same entity, period and XBRL context; separately define leases and financial-sector applicability.
- Interest Coverage: explicit EBIT and finance-cost definitions, with sector-specific exceptions.
- OCF: exact operating cash-flow fact, period, unit and cross-foot reconciliation.
- Store provenance per metric: `FinancialPeriodEnd`, `PublicationDate`, `AuditedStatus`, `ReportingBasis`, `Unit`, `Formula`, `SourceExchange`, `SourceURL`, `RevisionStatus`, `XbrlFactTag`, `ContextRef`, `EntityIdentifier`, `EvidenceSHA256`, `VerificationStatus`.

### D. Acceptance gate
Do not switch the production fundamental source/gate until:
- every current candidate has an issuer-identity-matched filing search result (including explicit no-filing/lookup-failed reason);
- every applicable metric is verified or explicitly marked inapplicable with sector policy;
- all metrics have period/basis/unit/formula/source provenance;
- central coverage and specialized audit reports agree;
- at least three issuers (one industrial, one financial-sector entity, one company with a prior mismatch) pass independent manual reconciliation;
- tests prove stale, revised, ambiguous, missing and conflicting filings fail closed.

## Files inspected in Run #335 artifact

- `volume_gainers_page_raw.csv`
- `volume_gainers_eod_research.csv`
- `fundamental_metric_coverage_by_stock.csv`
- `fundamental_metric_verification_summary.csv`
- `fundamental_source_compilation.csv`
- `fundamental_source_comparison_ecms.csv`
- `fundamental_filings_ecms.csv`
- `fundamental_filing_metadata_audit.csv`
- `fundamental_debt_equity_xbrl_audit.csv`
- `fundamental_ratio_xbrl_discovery.csv`
- `v8_fundamental_metric_verification.csv`
- `v8_fundamental_generated_evidence.csv`
- `volume_gainers_eod_summary.json`

No production code or main-branch files were modified by this audit.


## Addendum — live cohort blocker and overnight EOD recovery (18-Nov-2026)

### Why a fresh 18-Nov Top-25 was not available

- Scheduled EOD workflow Run #533 started at **01:28 IST on 18-Nov**, after its intended 17:01 IST slot on 17-Nov.
- The Python scheduler gate compared the current clock minutes (01:28) with the expected EOD clock (17:00) as if both were on the same calendar date. It therefore returned `SKIPPED / NOT_OFFICIAL_NSE_SESSION_SCAN_SLOT`.
- The EOD snapshot marker was not created, so the prior EOD state did not advance.
- Morning Run #541 then correctly failed closed: cached EOD page snapshot date was `2026-11-16`, while the latest completed NSE session was `2026-11-17`.
- The later successful PR-validation Run #540 did not execute a scan; route/EOD/Morning were skipped for the pull-request event. It is not a current Top-25 source.
- Therefore the 13-Nov / 23-equity cohort remains the last complete artifact available for this audit. Do not label it as the current 18-Nov cohort.

### Isolated recovery fix prepared

Draft PR #151: https://github.com/digitalmf78-pixel/AI-Trading-Bot/pull/151

- Branch: `fix/ecms-overnight-eod-recovery-2026-11-18`
- Change: allow scheduled EOD events delayed past midnight only before the next Morning window (before 09:15 IST).
- The existing `run_eod()` page-session-date guard remains mandatory: the fetched NSE page date must equal the latest completed NSE session or the run fails closed before saving the snapshot.
- Morning's narrow timing gate remains unchanged.
- Regression test added for the observed 18-Nov 01:28 IST case.
- **PR is draft and must not be merged until CI completes and the change is reviewed.** No production change has been merged.

### Official filing lookup recovery note

The seven missing NSE metadata rows are lookup gaps, not proof that no exchange filing exists. A direct NSE Archives announcement search surfaced an Aryaman Financial Services consolidated/standalone results announcement for the quarter ended 30-Sep-2026, approved 14-Nov-2026: https://nsearchives.nseindia.com/corporate/DALALSTCOM_16112026141955_Announcement.pdf . However, that announcement is not yet reconciled to an exact Integrated Filing XBRL record in the captured metadata ledger. It must remain a discovery lead, not a verified XBRL metric source.

No BSE fallback crawl for all seven unresolved symbols has been completed yet. The audit must not claim 23/23 official filing coverage until exact issuer identity, filing URL, period, audit label, basis and revision metadata are matched from NSE or BSE.

## Addendum — Q2 FY27 official filing recovery (18-Nov-2026)

This pass searched the last complete 23-stock cohort for newer results for the quarter ended **30-Sep-2026**. It is a filing-discovery and source-verification pass, not yet a complete seven-metric recomputation.

### Primary-source documents / records recovered

| Symbol | Primary evidence found | What is verified now | What is not yet verified |
|---|---|---|---|
| BELRISE | NSE Archives board outcome PDF, 13-Nov-2026 | Official unaudited standalone + consolidated Q2/H1 FY27 results; full statement includes revenue, expenses, finance costs, PBT/PAT and comparative periods. | Full seven-metric recomputation and balance-sheet/cash-flow component reconciliation. |
| CLCIND | NSE Archives Integrated Filing Ind-AS XBRL page, approved 02-Nov-2026 | Q2 FY27, standalone, unaudited; period and issuer identity match CLC Industries. | The retrieved page is filing metadata, not the full seven-metric source-fact reconciliation. |
| ORCHPHARMA | NSE Archives board outcome + Annexure-I PDF, 14-Nov-2026 | Official unaudited limited-reviewed standalone + consolidated Q2/H1 results. Revenue, finance costs, depreciation and PBT are visible in the statement. | Recompute all seven metrics; annual balance-sheet and cash-flow facts still need aligned official sources. |
| PRICOLLTD | NSE Integrated Filing — Financials page | Original unaudited Q2 FY27 filings exist for consolidated and standalone, both broadcast 04-Nov-2026. | Download and reconcile the underlying XBRL/details; filing existence alone does not verify metric values. |
| SONAL | NSE Archives newspaper-publication PDF, 14-Nov-2026 | Official announcement states Sonal Adhesives approved unaudited Q2/H1 results on 13-Nov-2026 and identifies its company investor-relations results page. | Actual results PDF/XBRL and all seven metrics still need retrieval. |
| ARYAMAN | Search produced a BSE/third-party announcement lead dated 14-Nov-2026, but the NSE Archives PDF previously surfaced as a supposed Aryaman filing is actually a DSJ Keep Learning newspaper advertisement. | No primary Aryaman results PDF/XBRL was successfully matched in this pass. Treat the earlier NSE URL association as a false-positive search match and do not use it. | Obtain exact Aryaman BSE/NSE filing and reconcile issuer identity, results and source facts. |

### Additional secondary-source leads — not accepted as verified metric evidence

- HINDADH: a secondary company-filings page reports Q2/H1 unaudited standalone and consolidated results approved 14-Nov-2026.
- KJMCFIN: a secondary BSE-announcement aggregator reports Q2/H1 unaudited standalone and consolidated results approved 11-Nov-2026.
- PBMPOLY: a secondary BSE-announcement aggregator reports unaudited standalone and consolidated Q2/H1 results approved 14-Nov-2026.
- SAPPL: a secondary BSE-announcement aggregator reports unaudited consolidated and standalone Q2/H1 results filed 14-Nov-2026.
- These are discovery leads only. No provider/aggregator values have been promoted to OFFICIAL_XBRL_VERIFIED.

### Primary-source references

- BELRISE official NSE Archives board outcome: https://nsearchives.nseindia.com/corporate/BELRISE_13112026183818_BELRISE_Outcome_of_Board_Meeting_13112026_FINAL.pdf
- CLCIND official NSE XBRL filing: https://nsearchives.nseindia.com/corporate/ixbrl/INTEGRATED_FILING_INDAS_208350_02112026184450_iXBRL_WEB.html
- ORCHPHARMA official NSE Archives results and limited review annexure: https://nsearchives.nseindia.com/corporate/ORCHPHARMA_14112026161414_Stx_Ltr_BM_Outcome.pdf
- PRICOLLTD NSE Integrated Filing search: https://www.nseindia.in/companies-listing/corporate-integrated-filing?integratedType=Integrated+Filing-+Financials&symbol=PRICOLLTD&tabIndex=equity
- SONAL official NSE Archives newspaper publication: https://nsearchives.nseindia.com/corporate/XTGLOBAL_14112026173102_merged__1_.pdf

### Updated decision

- New Q2 FY27 filing evidence exists for multiple cohort companies; the old annual-only coverage ledger is therefore stale as a complete description of latest filing availability.
- **No strict fundamental PASS is granted from this pass.** Quarterly P&L results alone cannot verify ROE, ROCE, Debt/Equity, Interest Coverage and OCF without aligned balance-sheet/cash-flow facts, correct formulas and matching consolidated/standalone basis.
- The 23-stock historical cohort remains the scope; it is not a newly generated current Top-25.
- Continue fail-closed. Keep every stock at WAIT_FOR_DATA until all applicable metrics and provenance are reconciled.
- Research only: no production code, workflows, cache, thresholds or NSE V8 files were changed.


## Addendum 2 — expanded Q2 FY27 filing recovery and interim trend check (18-Nov-2026)

### Scope
This pass searched the historical 23-symbol Run #335 cohort for Q2 FY27 (quarter ended 30-Sep-2026) filings. It does not represent a newly refreshed ECMS Top-25. Q2 unaudited data is used for current operating-trend context only; it is not substituted for the seven annual/TTM fundamental definitions.

### Filing evidence recovered

| Symbol | Q2 FY27 evidence | Evidence level |
|---|---|---|
| RPSGVENT | NSE Integrated Filing IndAS XBRL, consolidated, approved 05-Nov-2026; quarter and H1 data plus balance sheet and cash-flow sections | Primary NSE XBRL |
| BELRISE | NSE Archives result/press release; consolidated Q2 revenue ₹2,746.38 Cr, adjusted PAT ₹166.25 Cr (₹ Mn converted to Cr); board outcome confirms unaudited standalone and consolidated results | Primary NSE |
| TVSSCS | NSE Archives board outcome and results PDF; standalone + consolidated unaudited Q2/H1 with limited review; consolidated Q2 revenue ₹3,687.15 Cr, PAT ₹36.51 Cr | Primary NSE |
| PRICOLLTD | NSE Integrated Filing IndAS XBRL, consolidated and standalone originals, unaudited, approved 04-Nov-2026; full P&L, balance sheet and cash-flow sections | Primary NSE XBRL |
| CLCIND | NSE Integrated Filing IndAS XBRL, standalone, unaudited, approved 02-Nov-2026; full P&L, balance sheet and cash-flow sections | Primary NSE XBRL |
| TVSSRICHAK | NSE Archives board outcome confirms standalone + consolidated unaudited Q2/H1 results and limited-review reports, approved 14-Nov-2026 | Primary NSE |
| VIPCLOTHNG | NSE Archives newspaper extract and investor presentation; standalone Q2/H1 results, approved 13-Nov-2026 | Primary NSE |
| DSSL | NSE Archives Q2/H1 FY27 results press release; standalone + consolidated results; consolidated Q2 revenue ₹551.36 Cr and PAT ₹29.81 Cr | Primary NSE |
| DEEPAKFERT | NSE Archives Q2 FY27 results update; consolidated Q2 revenue ₹3,334 Cr and PAT ₹394 Cr | Primary NSE |
| UGROCAP | NSE Archives board outcome with consolidated Q2/H1 financial results; financial-services entity | Primary NSE |
| YATRA | Company investor-relations financial summary reports Q2 FY27 unaudited results; Q2 revenue ₹213.60 Cr and loss ₹2.353 Cr | Primary issuer website |
| ORCHPHARMA | NSE Archives board outcome and Annexure-I results/limited-review PDF, approved 14-Nov-2026 | Primary NSE |
| BOROLTD | Q2/H1 FY27 standalone + consolidated financial results and limited-review content recovered from filing mirror; exact issuer identity and period visible | Filing mirror; exchange-original URL still to be pinned |
| KAYNES | NSE Archives Q2 FY27 press release; consolidated Q2 revenue ₹952.5 Cr, PAT ₹39.8 Cr; H1 revenue ₹1,898.7 Cr, PAT ₹85.2 Cr | Primary NSE |
| GALLANTT | BSE filing listing confirms unaudited results for 30-Sep-2026; consolidated Q2 revenue ₹1,145.89 Cr and PAT ₹60.51 Cr | BSE listing/secondary mirror; exact original PDF still to be pinned |
| INDRAMEDCO | Q2 FY27 results recovered from filing mirror; quarter revenue ₹412.85 Cr, H1 revenue ₹819.00 Cr | Filing mirror; exchange-original URL still to be pinned |
| ARYAMAN | NSE Archives newspaper extract contains consolidated and standalone Q2/H1 results; consolidated total income ₹36.14 Cr, standalone PAT ₹5.49 Cr; financial-services business | Primary NSE newspaper extract |
| HINDADH | BSE filing mirror reproduces board outcome, limited review report, standalone/consolidated results, balance sheet and cash-flow sections; approved 14-Nov-2026 | Filing mirror of BSE submission; exchange-original URL still to be pinned |
| PBMPOLY | BSE announcement listing and extracted filing data report unaudited standalone/consolidated Q2/H1 and limited-review reports; Q2 consolidated revenue ₹47.74 Cr and PAT ₹3.04 Cr | BSE filing aggregator/mirror; original PDF not yet independently pinned |
| KJMCFIN | BSE filing record discovered for Q2/H1 unaudited standalone/consolidated results; financial-services business; reported Q2 consolidated PAT ₹7.52 Cr in filing extraction | BSE filing extraction; original PDF and all facts still to be pinned |
| MUKESHB | BSE filing extraction reports unaudited standalone/consolidated Q2/H1 results with balance sheet, cash flow and limited review; large one-quarter jump in financial income/profit; subsidiary review scope caveat | BSE filing extraction; original PDF still to be pinned |
| SONAL | NSE Archives newspaper extract confirms Q2/H1 unaudited results approved 13-Nov-2026; standalone Q2 revenue ₹41.46 Cr and PAT ₹0.203 Cr in extracted result | Primary NSE newspaper extract; results statement URL still to be pinned |

**Coverage result:** Q2 result evidence or a specific filing lead was found for all 23 historical cohort symbols. This is not the same as 23/23 direct exchange-XBRL verification: for BOROLTD, INDRAMEDCO, HINDADH, PBMPOLY, KJMCFIN, MUKESHB and GALLANTT, the exact exchange-original document/XBRL record still needs to be pinned and checked directly. The evidence register above deliberately separates primary exchange/issuer records from filing mirrors and aggregators.

### Specific XBRL facts independently read

**PRICOLLTD — consolidated, INR lakh, Q2 FY27**
- Filing identity: NSE symbol PRICOLLTD, ISIN INE726V01018; original, unaudited, quarter ended 30-Sep-2026; board approval 04-Nov-2026.
- Revenue from operations: ₹1,35,632 lakh (Q2); ₹2,46,176 lakh H1.
- Finance costs: ₹970 lakh Q2; ₹1,722 lakh H1.
- Depreciation/amortisation: ₹3,391 lakh Q2; ₹6,575 lakh H1.
- PAT: ₹8,521 lakh Q2; ₹15,223 lakh H1.
- H1 operating cash flow: ₹7,183 lakh.
- 30-Sep-2026 total equity: ₹1,40,616 lakh; borrowings: ₹8,222 lakh non-current + ₹42,858 lakh current; lease liabilities separately disclosed.
- This is a directly inspectable XBRL record, but the final seven-metric TTM calculation still needs prior-year same-basis comparative facts and a declared formula.

**CLCIND — standalone, INR lakh, Q2 FY27**
- Filing identity: CLC Industries Limited, NSE symbol CLCIND, ISIN INE376C01038; original, unaudited, quarter ended 30-Sep-2026; board approval 02-Nov-2026.
- Revenue from operations: ₹6,774.53 lakh Q2; ₹9,816.70 lakh H1.
- PAT: ₹85.15 lakh Q2; ₹133.06 lakh H1.
- Finance costs: ₹101.20 lakh Q2; ₹230.88 lakh H1.
- Depreciation/amortisation: ₹86.89 lakh Q2; ₹175.77 lakh H1.
- H1 operating cash flow: **negative ₹1,187.03 lakh**.
- 30-Sep-2026 equity: ₹257.62 lakh; borrowings: ₹5,066.08 lakh non-current + ₹3,225.40 lakh current. Lease liabilities are separately disclosed/limited in the captured XBRL.
- A raw borrowings/equity ratio from these fields is about **32.2x** before lease treatment. This does not reconcile with the older provider candidate D/E 55.96x. Do not use either value as final D/E until the exact debt definition and filing basis are reconciled.
- Equity is unusually small relative to borrowings; this requires a manual review and should not be hidden by a provider-derived ratio.

**TVSSCS — consolidated, INR crore, Q2 FY27**
- NSE board outcome confirms unaudited standalone and consolidated results with limited-review reports.
- Q2 revenue ₹3,687.15 Cr vs ₹2,662.63 Cr (+38.5%); Q2 PAT ₹36.51 Cr vs ₹16.31 Cr (+123.9%).
- H1 revenue ₹7,022.37 Cr vs ₹5,254.94 Cr (+33.6%); H1 PAT ₹58.99 Cr vs ₹87.47 Cr (-32.6%). Prior-year H1 includes a large share-of-profit/exceptional context; do not infer sustainable growth from the PAT percentage alone.
- Consolidated H1 operating cash flow ₹233.99 Cr vs ₹341.90 Cr in prior H1.
- The filing has both consolidated and standalone cash-flow statements; do not mix their facts.

### Interim trend flags (not a fundamental rating)

- **Positive Q2 revenue/PAT momentum:** BELRISE, TVSSCS, PRICOLLTD, DSSL, DEEPAKFERT, BOROLTD, ORCHPHARMA, PBMPOLY, ARYAMAN (financial services), KJMCFIN (financial services), UGROCAP (financial services).
- **Mixed or deteriorating profit despite revenue:** KAYNES (Q2 PAT sharply lower YoY), GALLANTT (PAT lower YoY), VIPCLOTHNG (PAT lower YoY), SONAL (PAT lower YoY), YATRA (Q2 loss and revenue down YoY), SAPPL (Q2 loss and revenue down YoY).
- **Special handling:** MUKESHB's large financial-services income/PAT jump needs source-level composition and subsidiary-scope review; CLCIND has negative H1 OCF and a very high raw debt/equity relationship; TVSSCS H1 PAT comparison is distorted by prior-year associate/exceptional items; UGROCAP, ARYAMAN, KJMCFIN and MUKESHB require financial-sector policy rather than industrial ROCE/D/E/interest-coverage rules.

### What remains before the seven fundamentals can be marked complete

1. Pin exact exchange-original PDF/XBRL URLs for the seven filing-mirror/aggregator cases above; confirm ISIN/security identity, original/revised status and consolidated/standalone.
2. Extract FY25, FY26 and H1 FY27 same-basis source facts for each stock. Compute TTM where possible as FY26 + H1 FY27 − H1 FY26; avoid mixing standalone and consolidated facts.
3. Use a single declared formula set:
   - Revenue Growth: latest audited FY26 vs FY25 annual revenue (and separately show H1 FY27 YoY trend).
   - Profit Growth: latest audited FY26 vs FY25 PAT, with exceptional items and minority interest treatment documented (and separately show H1 FY27 YoY trend).
   - ROE: TTM PAT attributable to owners / average opening and closing equity.
   - ROCE: TTM EBIT / average capital employed, with financial-sector entities marked N/A under a separate policy.
   - Debt/Equity: same-date interest-bearing borrowings / same-date equity, leases explicitly included or excluded by policy.
   - Interest Coverage: TTM EBIT / TTM finance cost, with sector-specific exclusions.
   - OCF: latest audited FY26 operating cash flow; show H1 FY27 interim OCF separately and do not annualise it without a stated method.
4. Reconcile the central verifier and dedicated Debt/Equity audit status contract. Do not promote any stock to strict PASS until all seven applicable metrics have primary-source facts, matching periods/basis/units and independently reproduced calculations.

### Current safe decision
This pass materially improves filing discovery, but it does **not** complete the seven-metric source reconciliation for 23/23 companies. Keep all 23 at WAIT_FOR_DATA; no strict fundamental PASS or FAIL is assigned. No production code, workflow, cache, threshold or NSE V8 file was changed.
