# Pilot Sample — Dividend and Corporate-Action Review

**Status:** official issuer / exchange evidence reviewed for INFY, ACI and AARTIIND. No bonus, split, rights issue or demerger requiring price-series adjustment was found in the reviewed event windows. Cash dividends are recorded separately.

| Symbol | Cash dividend ex-date | Record date | Amount/share | Treatment |
|---|---|---|---:|---|
| INFY | 10-Jun-2026 | 10-Jun-2026 | ₹25.00 | Added to gross dividend-inclusive simple-return estimate for horizons ending after ex-date |
| INFY | 03-Nov-2026 | 03-Nov-2026 | ₹26.00 | Recorded; after INFY 126-session endpoint (26-Oct), so not included in that horizon |
| ACI | 04-Jun-2026 | 05-Jun-2026 | ₹2.50 | Added to gross dividend-inclusive simple-return estimates for 21/63/126 sessions |
| AARTIIND | 11-Sep-2026 | 14-Sep-2026 | ₹1.00 | Added to 126-session simple-return estimate; outside 21/63-session endpoints |

## Stock-action review

- **INFY:** NSE corporate-action records reviewed for the 2026 event window show cash dividends and no bonus/split/rights/de-merger event in the window.
- **ACI:** FY2025-26 annual report states no bonus shares were issued during the preceding five years; reviewed exchange/company records show the FY26 cash dividend and no stock-action event in the pilot window.
- **AARTIIND:** FY2025-26 annual report share-capital reconciliation records PSOP share issuance and no bonus issue during FY2025-26; its historical 1:1 bonus predates the pilot by years. NSE quote/corporate-action records show the ₹1 FY26 cash dividend in September 2026 and no stock-action event in the pilot window.

## Official evidence

- INFY ₹25 final dividend ex-date 10-Jun-2026: [NSE corporate actions](https://www.nseindia.com/companies-listing/corporate-filings-actions?symbol=INFY&tabIndex=equity).
- INFY ₹26 interim dividend ex/record date 03-Nov-2026: [NSE-hosted Infosys board outcome](https://archives.nseindia.com/corporate/Infosys_23102026160704_BM_Outcome_Oct232026_1.pdf).
- ACI ₹2.50 final dividend recommendation and 05-Jun-2026 record date: [NSE-hosted company filing](https://nsearchives.nseindia.com/corporate/ARCHEAN_12052026010551_Record_Date_Intimation.pdf). Ex-date 04-Jun-2026: [MSE corporate-action record](https://www.msei.in/corporates/corporate-securities-information/corporate-update/default?symbol=ACI&type=4&vmode=vm). Stock-action review: [ACI FY26 annual report](https://www.archeanchemicals.com/investor-relations/admin/assets/products/ACIL%20Annual%20Report%2025-26.pdf).
- AARTIIND ₹1 final dividend ex-date 11-Sep-2026 and record date 14-Sep-2026: [NSE quote / corporate-actions page](https://www.nseindia.in/get-quote/equity/AARTIIND/Aarti-Industries-Ltd). Stock-action review: [AARTIIND FY26 annual report](https://nsearchives.nseindia.com/annual_reports/AR_30737_AARTIIND_2025_2026_A_22486837_27082026184733.pdf).

## Return calculation treatment

The event-study retains its original price-only close-to-close returns. A second, explicitly labelled gross cash-dividend-inclusive simple estimate is calculated as:

`(EndClose + GrossCashDividends - StartClose) / StartClose × 100`

Only dividends with ex-dates after the start session and on/before the horizon end are added. No reinvestment, taxes, fees, or official total-return index is modeled. Raw OHLC is not silently adjusted, so zone-touch and delivery/RVOL calculations remain based on the observed NSE cache rows.

Machine-readable evidence: `corporate_action_audit.csv` and `v8_cache_audit/official_calendar_corporate_action_audit.json`.
