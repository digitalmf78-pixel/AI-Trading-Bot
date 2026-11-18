# ECMS Bharat-SM-Data: Seven-Metric Source Audit (Initial Code Review)

**Scope:** Read-only review of the upstream `Sampad-Hegde/Bharat-SM-Data` library and ECMS's current `free_fundamental_sources.py` adapter/mapping.  
**Isolation:** Research branch only. No production workflow, fundamental thresholds, candidate selection, NSE V8, cache, or Telegram behavior changed.  
**Evidence type:** Static source-code review. No claim of live provider availability or issuer-level value accuracy is made in this report.

## Executive result

Bharat-SM-Data is a scraper/client for third-party Moneycontrol and Tickertape pages/endpoints, not an official filing feed. Its own README warns that it uses third-party private APIs and that third-party data accuracy cannot be guaranteed. Treat its output as unverified secondary observations only; official NSE/BSE filings remain the verification source.

One concrete ECMS mapping gap was found: **Operating Cash Flow (`OperatingCashFlowINR`) is not present in the current `ALIASES` mapping**, even though Moneycontrol/Tickertape cash-flow frames are fetched. Therefore the current seven-metric request cannot extract this metric through this adapter.

## Seven-metric audit matrix

| ECMS metric | Current intake path in adapter | Initial code-review finding | Safe status |
|---|---|---|---|
| Revenue Growth | Moneycontrol annual overview calculation; Tickertape income growth frames | Moneycontrol derives YoY only from annual columns matching FY20xx and a positive prior-year base. Period is emitted as an FY-pair label, not a filing period end/publication date. Tickertape extraction uses generic row/column selection. | Secondary observation only; period and formula need issuer-level reconciliation |
| Profit Growth | Same annual overview / Tickertape growth frames | Same period limitation. Negative/zero prior-year profit bases are not calculated by the Moneycontrol helper; transition cases need explicit handling rather than a numeric growth claim. | Secondary observation only; transition cases must remain uncomputed/flagged |
| ROE | Ratios/overview/scorecard/income/balance-sheet frames via aliases | Generic extractor returns the first numeric cell it encounters; no metric-specific formula, denominator average, or explicit period-end/basis validation at extraction time. | Unverified until matched to same-period official filing calculation |
| ROCE | Same generic extraction path | Same risk: label match alone does not establish formula, denominator convention, period, or reporting basis. | Unverified until matched to same-period official filing calculation |
| Debt/Equity | Same generic extraction path | Label match alone does not establish whether debt includes borrowings/lease liabilities or whether equity and debt use matching period/basis. | Unverified until reconciled to a defined official XBRL calculation |
| Interest Coverage | Same generic extraction path | Label match alone does not establish EBIT/interest definition or treatment of finance costs; period/basis are not validated by the extraction helper. | Unverified until formula and official filing context are reconciled |
| Operating Cash Flow | Cash-flow frames are fetched from both providers | **Missing from `ALIASES` in the current shared adapter.** No mapping for `OperatingCashFlowINR` means it cannot be selected through the seven-metric alias pipeline. | Not available through current mapping; do not infer or substitute another cash-flow line |

## Cross-cutting implementation risks

1. **No standalone comparison in the Moneycontrol calls:** the current adapter explicitly requests `statement_type="consolidated"` for ratios, overview, income, balance sheet and cash flow. This is not evidence that the values match a standalone filing.
2. **First numeric value selection:** `_extract_ratio_observation()` returns the first numeric cell in a matching row/column. It does not independently sort periods or prove that the first cell is the latest completed reporting period.
3. **Period provenance is weak for generic ratios:** the returned period is the raw table column label. It is not normalized to an explicit financial period end and is not paired with a verified publication date.
4. **Annual growth is narrow:** `_extract_annual_growth()` accepts FY-style year headers, requires consecutive years and a positive prior-year base, and calculates a simple percentage change. It does not establish whether the source's row is audited, restated, or comparable across reporting basis.
5. **Unit normalization is not sufficient proof:** the scalar parser removes currency/scale tokens (₹, Rs, INR, crore, lakh) and percent markers. It must not be used to silently convert absolute cash-flow amounts without a separately verified scale/unit contract.
6. **Upstream identity behavior:** upstream Moneycontrol `get_ticker()` can return the first search result's `sc_id` together with the full result list when exact `stock_name` matching fails. The ECMS research adapter contains a stricter exact-hit wrapper; preserve this fail-closed behavior.
7. **Tickertape selection:** ECMS filters search results by exact NSE ticker, but takes the first matching hit. Duplicate exact ticker hits should be treated as ambiguous rather than silently selecting index zero.
8. **Private/unstable endpoints:** upstream README explicitly describes third-party private APIs. Responses can change, fail, or be rate-limited; successful parsing is not official verification.

## Required next research steps

- Add a focused test proving that `OperatingCashFlowINR` is currently unmapped, then design an exact cash-flow label mapping only after inspecting real provider table schemas for multiple issuers.
- Capture raw, non-published diagnostic table schemas for a small issuer sample, separately for Moneycontrol and Tickertape. Record exact issuer identity, source URL, retrieval timestamp, raw label, period label, reporting basis, unit/scale and selected cell.
- Verify both consolidated and standalone observations where available. Do not combine them or choose whichever value is populated.
- For ROE, ROCE, Debt/Equity and Interest Coverage, document the exact numerator/denominator formula and reporting period before accepting any provider label.
- For Revenue/Profit Growth, reconcile the exact consecutive FY pair, audited/restated status, and treatment of zero/negative prior-year bases.
- For Operating Cash Flow, reconcile the exact cash-flow statement line, INR scale (rupees/thousands/lakhs/crores), annual vs YTD period, and whether interim figures are cumulative.
- Compare sample observations to issuer-matched NSE/BSE official filings/XBRL with identical period and basis. Record mismatch reasons; never average sources.
- Keep all provider values `NOT_OFFICIALLY_VERIFIED` until that field-level reconciliation succeeds. Missing, ambiguous, stale or mismatched observations remain `WAIT_FOR_DATA` / unverified.

## Explicit non-goals

This audit does not change the existing seven-metric fundamental gate, thresholds, candidate inclusion, production data, scheduled workflows, cache, Telegram, NSE V8, or trading behavior. It does not authorize use of third-party values as official data.

## Issuer sample comparison — FY 2025-26 (public-page evidence)

**Retrieval date:** 2026-11-18. **Important limitation:** The connected environment did not execute Bharat-SM-Data's private Moneycontrol/Tickertape API calls. The values below are publicly surfaced Moneycontrol pages and Tickertape screeners, used as *provider-page proxies* to test whether the same labels can be reconciled to official annual reports. They are not represented as raw outputs from the ECMS adapter. The exact adapter-level live capture remains outstanding.

### 1) INFOSYS

| Metric | Public provider-page observation | Official company evidence | Reconciliation |
|---|---:|---:|---|
| Revenue | Moneycontrol FY26 ₹1,78,650 cr | Consolidated FY26 revenue ₹1,78,650 cr; FY25 ₹1,62,990 cr; growth 9.6% | Value agrees; annual period and consolidated basis agree in the official report |
| Profit | Moneycontrol FY26 net profit ₹29,474 cr | Consolidated net profit ₹29,474 cr; owner-attributable profit ₹29,440 cr; FY25 owner-attributable ₹26,713 cr | Headline net profit agrees; for profit-growth use a consistently defined PAT row. Owner-attributable growth is about 10.2% |
| Revenue growth | Adapter's Moneycontrol helper calculates from annual revenue columns | Official consolidated growth 9.6% | Same result if the row and FY pair are identical |
| Profit growth | Adapter helper uses a positive prior-year base | Owner-attributable PAT ₹29,440 cr vs ₹26,713 cr | About 10.2%; provider helper's row choice must be confirmed before accepting |
| ROE | Moneycontrol 31.70%; Tickertape screener 31.07% | Annual-report headline ROE 31.6% | Close, but Tickertape is not exact; formula/basis need explicit confirmation |
| ROCE | Moneycontrol 40.23%; Tickertape 39.63% | No directly comparable consolidated ROCE figure located in the reviewed annual-report ratio table | Unverified |
| Debt/Equity | Moneycontrol 0.00; Tickertape screener 0.00 | Official consolidated ratio 0.1; report says debt represents only lease liabilities | Not an exact match; definition/rounding/basis discrepancy |
| Interest coverage | Moneycontrol 112.02x | Official consolidated ratio 97.1x; report says this is primarily lease interest | Material difference; do not accept provider value without formula reconciliation |
| Operating cash flow | No mapped adapter value | Official AGM material reports consolidated operating cash flow ₹35,824 cr for FY26 | Adapter currently cannot return this metric because OperatingCashFlowINR is unmapped |

### 2) HDFC BANK

| Metric | Public provider-page observation | Official company evidence | Reconciliation |
|---|---:|---:|---|
| Revenue | Moneycontrol FY26 ₹3,48,615 cr | Annual report FY26 net revenues ₹1,91,218.6 cr | Different revenue concepts/rows; not comparable without a bank-specific mapping |
| Profit | Moneycontrol FY26 ₹79,219 cr | Annual report FY26 PAT ₹74,671.3 cr | Mismatch; source row and basis unresolved |
| ROE | Moneycontrol 12.97%; Tickertape screener 13.26% | Annual report FY26 ROE 14.3% | Does not reconcile; likely formula/period/basis differences remain unresolved |
| ROCE | Tickertape screener 5.62% | No comparable conventional ROCE accepted for a bank in this audit | Do not use industrial ROCE gate on banks without a separately designed bank-specific metric |
| Debt/Equity | Tickertape screener 0.00 | Annual report discloses borrowings ₹4,89,394.6 cr and shareholders' funds ₹5,62,900.91 cr | Generic D/E is not a sound bank solvency measure; 0.00 must not be interpreted as zero borrowings |
| Interest coverage | No comparable verified provider/official pair captured | Bank interest expense/income are core operating flows | Generic industrial interest-coverage formula is unsuitable without bank-specific definition |
| Operating cash flow | No mapped adapter value | Bank cash-flow statement exists, but operating cash flow is heavily affected by deposits/advances | Do not apply a non-financial-company OCF threshold to banks |

**Bank-specific conclusion:** HDFC Bank is a deliberate sector edge case, not a clean validation issuer for generic industrial Revenue Growth / ROCE / Debt-to-Equity / Interest Coverage / Operating Cash Flow. Keep bank-specific ratios and definitions separate; do not coerce the bank into industrial formulas.

### 3) RELIANCE INDUSTRIES

| Metric | Public provider-page observation | Official company evidence | Reconciliation |
|---|---:|---:|---|
| Revenue | Moneycontrol FY26 ₹10,57,035 cr | Consolidated FY26 Revenue from Operations ₹10,75,675 cr; Value of Sales & Services ₹11,75,919 cr | Provider page's revenue row does not match either official headline row; row definition must be identified |
| Profit | Moneycontrol FY26 PAT ₹95,610 cr | Consolidated PAT before share of associates/JVs ₹95,610 cr; profit for year after share of associates/JVs ₹95,754 cr | Exact match to PAT-before-associates row; do not confuse it with profit for year |
| Revenue growth | Not accepted from provider page until revenue row is identified | Official Revenue from Operations grew from ₹9,80,136 cr to ₹10,75,675 cr (about 9.75%) | Provider growth remains unverified |
| Profit growth | Not accepted until PAT row is confirmed | PAT-before-associates ₹95,610 cr vs ₹80,787 cr; profit-for-year ₹95,754 cr vs ₹81,309 cr | Different valid profit rows yield different growth; label must specify which row |
| ROE | Moneycontrol 8.93%; Tickertape page not conclusively issuer-period matched | Reviewed official standalone ratio is 8.5%; consolidated ROE still needs exact same-basis confirmation | Not comparable yet; basis is unresolved |
| ROCE | No exact same-basis provider/official pair captured | Standalone report's ROCE is 20.7%; formula is explicitly defined in the report | Must not compare to a consolidated provider ratio or substitute a generic formula |
| Debt/Equity | Moneycontrol 0.41 | Official standalone ratio 0.41 | Numeric match, but it does not validate the adapter's consolidated call; confirm basis before use |
| Interest coverage | No exact same-basis provider/official pair captured | Official integrated report states interest coverage rose to 8.83x in FY26 from 5.59x in FY25 | Provider observation still required and formula must be aligned |
| Operating cash flow | No mapped adapter value | Official consolidated net cash flow from operating activities ₹1,92,113 cr; FY25 ₹1,78,703 cr | Official line and INR-crore scale identified; adapter mapping remains absent |

### What this sample proves — and what it does not

1. Public Moneycontrol/Tickertape values can look plausible while differing from official values or using different line definitions. Infosys interest coverage and debt/equity, HDFC Bank ROE/revenue/profit, and Reliance revenue illustrate why label-only acceptance is unsafe.
2. A matching number does not prove the correct basis. Reliance Moneycontrol D/E 0.41 matches the official **standalone** ratio, while the adapter explicitly requests **consolidated** Moneycontrol statements.
3. HDFC Bank must not be used to validate industrial-company formulas. Its revenue, leverage and cash-flow concepts need a bank-specific schema.
4. The seven-metric data gate must remain closed for any field without a verified issuer, FY/period, basis, unit and formula.
5. **No raw private-API table capture has yet been made.** Before changing adapter logic, the next controlled run must capture the actual Bharat-SM-Data frames for these three symbols, both providers separately, with source URL, retrieval timestamp, raw row label, ordered period columns, selected value and unit. Duplicate exact Tickertape hits must be flagged as ambiguous.
