# ECMS official-source coverage audit — 2026-11-20

**Scope:** ECMS research only. No production metric mapping, provider logic, scan selection, NSE V8 source/workflow/configuration, or shared provider code is changed by this report.

## 1. BSE official source findings

### Verified official filing surfaces

SEBI's corporate-filings curation page explicitly links BSE Financial Results to:
- Financial Results: https://www.bseindia.com/corporates/Comp_Resultsnew.aspx
- XBRL filing details: https://www.bseindia.com/corporates/xbrldetails.aspx
- General corporate announcements: https://www.bseindia.com/corporates/ann.html

Source: https://www.sebi.gov.in/curation/corporate_filings.html

BSE's official circular compilation confirms:
- Equity-listed entities must submit financial results in XBRL mode using the **Integrated Filing – Financial** utility in the BSE Listing Centre.
- The PDF result and the XBRL filing are separate filing artefacts/workflow steps; the XBRL filing is required on the same date as PDF submission under the 2025 integrated-filing instructions.
- Earlier BSE instructions required Regulation 33/52 financial results in XBRL within 24 hours of PDF submission, with an insurance-company exception in that older instruction.
- BSE has a Listing Centre XBRL utility and an XBRL helpdesk.

Official source: https://www.bseindia.com/markets/MarketInfo/DownloadAttach.aspx?attachedId=6b163bb8-fbe3-4e14-be9a-47b99f2cfaaf&id=20250523-40
Relevant source passages: pages 88–92 of the circular compilation (PDF page labels 88–92).

### API conclusion — do not implement a guessed endpoint

BSE's official circular describes **API-based integration between the two stock exchanges** so a filing made on one exchange can be disseminated to the other. It describes an exchange-to-exchange single-filing mechanism, not a public consumer retrieval API contract for ECMS.

Official source: same BSE circular compilation, section “Introduction of the single filing system through API-based integration between Stock Exchanges”; the stated purpose is automatic dissemination between exchanges.

BSE also advertises a separate official **Self Data Feed** portal with Corporate Data APIs covering company financials, disclosures, corporate announcements and actions. Its stated onboarding requires registration/KYC, selection of data plans, agreement to pricing and payment; it advertises limited free trial access. This is a legitimate route to obtain a licensed, supported data feed, but the public landing page does not expose the technical endpoint/schema/manual itself. Portal: https://marketdata.bseindia.com/

The official pages, circulars and product portal reviewed establish that BSE financial-result and XBRL filings exist and that a licensed Corporate Data API product is offered. They do **not** establish a freely accessible, documented public GET API contract for ECMS retrieval (endpoint, query schema, pagination, rate limits, response schema, retention, and access terms). BSE's public filing pages returned HTTP 403 to this research fetch, so no unauthenticated live response contract could be validated in this audit.

Third-party references to undocumented `api.bseindia.com/BseIndiaAPI/api/...` routes are not sufficient authority to build a production adapter. They may be investigated only as leads in an isolated test, with exact request/response evidence and without bypassing access controls. No BSE API adapter should be merged until BSE documents or otherwise authoritatively confirms the retrieval contract and a repeatable capture is validated.

### Recommended BSE source order for a future ECMS adapter

1. BSE Financial Results/XBRL official filing surface and its official XBRL/Integrated Filing – Financial documents.
2. Exact issuer filing attachments and their own XBRL instance/schema/taxonomy evidence, where publicly retrievable.
3. Issuer annual/quarterly report only as a separate document source, not silently substituted for an exchange XBRL filing.
4. Never infer a BSE XBRL URL from a PDF URL, NSE URL, scrip code, or undocumented filename pattern.

For every future capture retain issuer identity (BSE scrip code, symbol, ISIN), filing period, publication/revision time, audited/unaudited label, standalone/consolidated basis, source URL, HTTP metadata, payload hash, taxonomy, context, dimensions, unit, decimals, and pagination/coverage status. Keep BSE and NSE captures as distinct evidence records; do not merge them solely because the issuer and period appear similar.

## 2. NSE filing coverage audit — latest completed ECMS EOD artifact

Audited artifact: ECMS EOD run `44565807604`, dated 2026-11-19.
Run URL: https://github.com/digitalmf78-pixel/AI-Trading-Bot/actions/runs/44565807604

The EOD scan captured 25 NSE Volume Gainers page rows, of which 23 were Main Board eligible. ECMS queried the NSE Integrated Filing endpoint once for each of the 23 eligible symbols.

### Capture-level results

- 23 unique NSE filing API request evidence IDs for 23 symbols.
- All 23 requests returned HTTP 200.
- Every request used page 0 and requested size 1000.
- Pagination was not exposed in the captured response envelope: **all 23 requests are classified `PAGINATION_NOT_EXPOSED_SINGLE_PAGE_ONLY`**.
- Therefore a short response is not proof that the symbol has no older/other filing pages. This is a coverage limitation, not a verified absence.
- The metadata output contains 45 filing rows: 43 explicit metadata rows and 2 no-eligible-filing rows.
- The two zero-record symbols were BLUECLOUDS and ODYCORP. Their current result is “no eligible filing returned by this capture”, not proof that no filing exists.

NSE endpoint observed in the ECMS artifact:
`https://www.nseindia.com/api/integrated-filing-results`

Request shape observed (example; values vary by symbol):
`index=equities, page=0, period_ended=all, size=1000, symbol=<symbol>, type=Integrated Filing- Financial`

### Filing/metric verification results in the same EOD artifact

- Filing metadata summary: 14 metric rows across 14 symbols matched; 9 metric rows across 9 symbols had `FILING_URL_MISSING`.
- Metric verification summary: 21 observations `OFFICIAL_XBRL_VERIFIED`; 18 `PROVIDER_VALUE_MISMATCH`; 70 `DERIVED_RECONCILIATION_REQUIRED`; 68 `FILING_METADATA_NOT_CONFIRMED`; 2 `PROVIDER_ONLY`; 1 `PROVIDER_VALUE_WITHIN_XBRL_ACCURACY`.
- ROE, ROCE, and Interest Coverage discovery found 12 candidate facts, but all were discovery-only; 37 filings had no matching candidate tag and 2 did not have a unique exact filing. None of these candidate facts is promoted to a verified metric.
- Debt/Equity audit: 17 provider mismatches, 1 official XBRL verified, 1 within XBRL accuracy interval, 1 missing provider value, 1 missing filing URL, and 2 financial-sector rows marked not applicable.

### Required next NSE capture improvement

The next ECMS-only change should be a bounded pagination/coverage investigation of the observed NSE endpoint:
- Inspect the actual response envelope and frontend request contract for an explicit total-page/total-record field or continuation token.
- If pagination is exposed, enumerate every page within a strict per-symbol/page/byte/time cap and record every page's hash and coverage.
- If pagination is not exposed, preserve `PAGINATION_NOT_EXPOSED_SINGLE_PAGE_ONLY`; do not relabel a short page as complete.
- Distinguish `NO_ELIGIBLE_NSE_FILING` from `SOURCE_CAPTURE_INCOMPLETE` and `SOURCE_CAPTURE_FAILED`.
- Do not allow an incomplete capture to turn into a verified filing absence or to unlock a provider-only metric.

## 3. ECMS metric remediation order

Based on the same artifact, recommended order after source-coverage work:

1. Resolve exact issuer + period + filing variant + audited status + standalone/consolidated basis and revision selection.
2. Reconcile the 18 provider mismatches using source-specific formula and XBRL accuracy intervals; do not overwrite raw provider values.
3. Implement component-level reconciliations for derived metrics (ROE, ROCE, Interest Coverage, Debt/Equity) only after the exact statement facts, taxonomy definitions, contexts, units and periods are verified.
4. Keep all unknown, missing, ambiguous, partial-pagination and unsupported cases as `WAIT_FOR_DATA` / unverified.
5. Keep the `MASKINVEST` RVOL issue separate from fundamental verification and investigate only in ECMS.

## 4. Change decision

**No BSE adapter is approved by this audit.** The authoritative BSE filing surfaces are confirmed, but a public retrieval API contract has not been verified. The immediate safe implementation candidate is an ECMS-only NSE pagination/coverage enhancement, preceded by a fixture-backed response-envelope audit. Production fundamental mappings and NSE V8 remain unchanged.

---
Audit inputs: ECMS EOD artifact `ecms-volume-gainers-eod-44565807604` and official SEBI/BSE links above. The artifact is a dated snapshot (2026-11-19), not a live statement of current filing availability.
