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
