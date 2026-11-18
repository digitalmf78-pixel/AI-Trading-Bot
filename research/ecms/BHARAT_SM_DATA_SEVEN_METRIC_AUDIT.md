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
