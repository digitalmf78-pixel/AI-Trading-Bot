# ECMS — Bharat-SM-Data Fundamental Source Audit

**Audit date:** 2026-11-17  
**Scope:** Research only; isolated branch `research/bharat-sm-data-fundamental-audit-2026-11-17`.  
**Upstream reviewed:** `Sampad-Hegde/Bharat-SM-Data`, branch `master`, source files inspected at the revisions listed below.  
**Decision:** Do not add this package to the ECMS production workflow or production requirements on the basis of this code inspection.

## 1. Scope and evidence standard

This is a source-code capability audit, not a live-data validation. The upstream client methods and their intended return structures were inspected. No live provider requests, sample-company payloads, period/value reconciliations or terms-of-use approvals were completed in this pass.

A metric is **method-supported** only when an upstream method exposes a relevant statement or ratio table. It is **not confirmed available** until a real response for an exact NSE issuer has been inspected and its field name, unit, period, basis and calculation are validated.

## 2. Seven-metric availability matrix

| Required metric | Screener module | MoneyControl module | Tickertape module | Audit conclusion |
|---|---|---|---|---|
| Revenue Growth | `Screener.py` advertises `Sales growth`, multi-year sales-growth fields and quarterly growth fields; P&L/quarterly tables also exist. | Annual/quarterly P&L methods return statement tables from which growth may be derived only across explicitly matched periods. | `get_income_data(..., view_type='growth')` supports growth-view retrieval. | Method-supported; exact FY/quarter field mapping and growth formula not runtime-confirmed. |
| Profit Growth | Advertises `Profit growth`, multi-year profit-growth and quarterly profit-growth fields; P&L tables exist. | P&L statement tables expose the underlying statement data; derived growth requires consecutive period matching and positive prior-period base. | Income growth view exists. | Method-supported; exact profit definition (PAT/continuing operations/etc.) and period mapping not runtime-confirmed. |
| ROE | Advertises `Return on equity` and historical/average ROE fields; Ratios table method exists. | Ratios mini/complete statement methods exist. | `get_key_ratios()` extracts the page's `securityInfo.ratios` object. | Ratio retrieval exists; exact key, value unit, date and basis require sample payload validation. |
| ROCE | Advertises `Return on capital employed`, historical/average ROCE fields and `ROCE3yr avg`. | Ratios methods exist; exact ROCE key not confirmed from code alone. | Key-ratios object exists; exact ROCE key not confirmed. | Screener field is advertised; other providers require payload inspection. |
| Debt/Equity | Advertises `Debt to equity` and related leverage fields. | Balance-sheet and ratios methods exist; exact debt/equity definition and key require payload inspection. | Balance-sheet and key-ratios methods exist; exact key and definition require payload inspection. | Method-supported; denominator/debt components and basis not runtime-confirmed. |
| Interest Coverage | Advertises `Interest Coverage Ratio` and `Interest Coverage`. | Ratios methods exist; exact key/definition require payload inspection. | Key-ratios object exists; exact key/definition require payload inspection. | Screener field is advertised; MC/TT values remain unconfirmed until sample payload inspection. |
| Operating Cash Flow | Advertises `Cash from operations last year`, preceding-year and 3/5/7/10-year operating-cash-flow fields; Cash Flow table method exists. | Mini and complete cash-flow statement methods exist. | `get_cash_flow_data()` returns annual cash-flow data. | Statement retrieval exists; exact row label, currency/scale, annual period and operating-cash-flow sign convention require payload inspection. |

## 3. Provider-specific implementation findings

### Screener

- Relevant methods: `get_ticker()`, `get_base_tables()`, `get_profit_and_loss()`, `get_balance_sheet()`, `get_cash_flow()`, `get_ratios()`.
- The source advertises many of the required metric labels, including sales/profit growth, ROE, ROCE, debt/equity, interest coverage and cash-from-operations fields.
- **Blocking finding:** the constructor initializes `_login_csrf_token = None`. The inspected `get_base_tables()` returns a table only when the HTTP response is 200 **and** `_login_csrf_token is not None`. The token is set only in the username/password login path. Therefore, this upstream implementation does not establish the no-login/public-access behavior required by the current ECMS policy. Do not enable login automation or pass credentials to work around this.
- The README's no-login/open-source description must not be treated as proof that this class works anonymously.

### Moneycontrol

- Relevant methods: `get_ticker()`, `get_profit_loss_mini_statement()`, `get_balance_sheet_mini_statement()`, `get_cash_flow_mini_statement()`, `get_ratios_mini_statement()`, `get_complete_profit_loss()`, `get_complete_cashflow_statement()`, `get_complete_ratios_data()`.
- The implementation calls website widget/autosuggestion endpoints and parses HTML tables; the upstream README explicitly describes third-party private APIs/scraping and warns that accuracy and permissions are not guaranteed.
- Mini statement methods default to consolidated; complete statement methods default to standalone. The caller must pass the intended basis explicitly and persist the returned basis with every observation.
- The ECMS wrapper's strict Moneycontrol identity matching is a useful existing safeguard, but it does not prove financial-period alignment or field correctness.
- No sample response was validated in this audit.

### Tickertape

- Relevant methods: `get_income_data()`, `get_balance_sheet_data()`, `get_cash_flow_data()`, `get_key_ratios()`.
- Income retrieval supports interim/annual horizon and normal/growth/margin views. Balance sheet and cash-flow retrieval are annual in the inspected implementation.
- `get_key_ratios()` parses the website's embedded `__NEXT_DATA__` JSON and extracts `securityInfo.ratios`; this is an undocumented page structure, not a supported official API contract.
- Exact ratio keys, units, period dates and reporting basis were not established from method signatures alone.

## 4. Licensing, reliability and operating constraints

- The upstream repository includes an Apache License 2.0 file. This does not grant permission to scrape, redistribute or automate access to third-party provider websites.
- The upstream README expressly warns that it uses third-party private APIs and that users must consider permissions, copyright and accuracy.
- The library's own license and the data providers' website terms are separate questions. No production use is approved by this audit.
- The package has runtime dependencies including requests, pandas, pydash, BeautifulSoup, html5lib, lxml and Brotli. Dependency pinning, transitive security review, rate-limit behavior and reproducible installation have not yet been tested in the ECMS workflow.
- No live endpoint, scraping or scheduled workflow has been run as part of this source inspection.

## 4A. Additional ECMS adapter defect found during cross-check

A follow-up inspection of the existing shared `free_fundamental_sources.py` adapter found that the required metric `OperatingCashFlowINR` was not present in its `ALIASES` mapping. The collector constructs its requested metric set from that mapping, so the seven-metric secondary-source request silently omitted Operating Cash Flow. The parser also had no label aliases with which to extract this metric from fetched cash-flow tables.

On this isolated branch only:
- Added candidate row-label aliases for operating cash flow.
- Added a fixture test using a Moneycontrol-style cash-flow table with a dated observation.
- The fixture is intended to prove metric selection, extraction and period/source-URL capture; it does **not** prove live provider responses use those labels or that the numeric unit/scale is INR.

This is a source-mapping fix under research validation, not production approval. The seven-metric audit remains open until live provider payloads and official filings confirm exact labels, units, periods and basis.

## 5. ECMS integration decision

1. Keep the current ECMS production provider configuration unchanged.
2. Do not use the upstream Screener class for automated no-login retrieval unless a compliant, non-login path is independently demonstrated and approved. Current inspected code does not demonstrate one.
3. Treat Moneycontrol and Tickertape strictly as secondary provider observations. Never label them official or use them to overwrite existing Yahoo/official filing values.
4. Before considering any adapter, test a small, explicitly selected sample of NSE Main Board issuers on the isolated research branch only. Record exact NSE symbol-to-provider identity evidence; reject ambiguous matches.
5. For each of the seven metrics, retain raw provider label, raw value, normalized value, unit/currency/scale, financial period end, publication/retrieval date, standalone/consolidated basis, calculation formula and source URL.
6. Compare only observations with identical issuer, metric definition, period, basis and unit. Do not average conflicting values.
7. Reconcile provider observations against the corresponding NSE/BSE official filing and XBRL facts. Preserve mismatch reasons; do not promote a provider value to official verification.
8. A bank/NBFC/insurer must use sector-specific applicability and definitions; do not apply industrial-company ratios blindly.
9. Any missing, ambiguous, stale, misaligned or conflicting metric remains `WAIT_FOR_DATA`; provider failure must not drop the Volume Gainer candidate from other research layers.

## 6. Next audit tasks

- [ ] Inspect the existing ECMS `free_fundamental_sources.py` and `fundamental_source_compilation.py` mappings against the upstream methods, without changing shared provider behavior.
- [ ] Design a fixture-based parser contract for the seven metrics (including raw labels, units, period and basis).
- [ ] Only if provider terms and access method permit it, perform a bounded sample retrieval for a few unambiguous Main Board issuers on this branch.
- [ ] Reconcile each sample metric with the exact official filing period and basis.
- [ ] Add automated tests for missing fields, wrong units/scales, mismatched periods/bases, duplicate identity matches and provider failures.
- [ ] Present evidence and obtain approval before proposing any production integration.

## 7. Upstream source revisions inspected

- `Bharat_sm_data/Fundamentals/Screener.py` — blob SHA `972619d5f08f83787d7e24c5586d8106f2364520`.
- `Bharat_sm_data/Fundamentals/MoneyControl.py` — blob SHA `0360cabde75c36ea2794700d9a686ddea95ca7d4`.
- `Bharat_sm_data/Fundamentals/TickerTape.py` — blob SHA `2d9372fcd457140f4da0f58b349038cacc184d2c`.
- Upstream README and LICENSE were inspected on `master` on 2026-11-17.

## 8. Safety boundary

This audit document is research evidence only. It does not change ECMS production workflows, NSE V8, shared provider settings, production thresholds, production caches or scanner behavior. It does not authorize live trading, orders, backtesting or basket construction.
