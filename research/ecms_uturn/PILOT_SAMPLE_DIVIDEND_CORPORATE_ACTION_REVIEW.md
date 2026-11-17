# Pilot Sample — Cash Dividend / Corporate-Action Review

**Status:** partial review only. No split/bonus/de-merger price adjustment has been applied. All price-only outcomes remain provisional.

| Symbol | Cash dividend evidence during post-result window | Date evidence | Treatment in current event study |
|---|---|---|---|
| INFY | ₹25 final dividend; ₹26 interim dividend | NSE corporate-actions page lists ₹25 ex-date 10-Jun-2026; Infosys filing states ₹26 interim dividend ex/record date 03-Nov-2026 | Ex-dates fall within the observed post-result window. Cash dividends are excluded from reported price-only returns. |
| ACI | ₹2.50 final dividend per ₹2 share recommended for FY2025-26 | Company filing dated 11-May-2026 gives record date 05-Jun-2026; exact ex-date still needs independent NSE action-table verification | Cash dividend excluded from reported price-only returns. |
| AARTIIND | ₹1.00 final dividend per ₹5 share recommended for FY2025-26 | Company/NSE notice gives record date 14-Sep-2026; exact ex-date still needs independent NSE action-table verification | Cash dividend excluded from reported price-only returns. |

## Official evidence

- INFY ₹25 dividend ex-date 10-Jun-2026: [NSE corporate actions page](https://www.nseindia.com/companies-listing/corporate-filings-actions?symbol=INFY&tabIndex=equity).
- INFY ₹26 interim dividend ex/record date 03-Nov-2026: [Infosys board outcome](https://archives.nseindia.com/corporate/Infosys_23102026160704_BM_Outcome_Oct232026_1.pdf).
- ACI ₹2.50 final dividend recommendation and 05-Jun-2026 record date: [NSE-hosted company filing](https://nsearchives.nseindia.com/corporate/ARCHEAN_12052026010551_Record_Date_Intimation.pdf).
- AARTIIND ₹1.00 final dividend recommendation and 14-Sep-2026 record date: [NSE-hosted notice](https://nsearchives.nseindia.com/corporate/AARTIIND_28082026144106_AARTIIND_Newspaper.pdf).

## Consequence

The event-study 21/63/126-session figures are **price-only close-to-close observations**, not total shareholder returns. Dividend cash has not been added back, and tax/reinvestment are not modeled. Before promoting any return comparison, reconcile exact ex-dates and calculate a separately labelled dividend-inclusive total-return series. Do not silently adjust the raw OHLC series used for target-zone touch detection.
