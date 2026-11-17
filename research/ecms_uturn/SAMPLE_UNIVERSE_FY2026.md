# ECMS U-Turn FY2026 sample universe — research only

**As of:** 17-Nov-2026  
**Scope:** 3 NSE Main Board issuers; annual diluted EPS only; consolidated basis for both FYs.  
**Important:** This is a source-verified EPS/event sample, not a completed U-Turn calculation. The 20-session OHLC peak and post-result close are intentionally blank until obtained from official NSE historical price records and reconciled for corporate actions.

| NSE symbol | Issuer | FY2025 diluted EPS (₹) | FY2026 diluted EPS (₹) | Result approval date/time (IST) | EPS direction |
|---|---|---:|---:|---|---|
| INFY | Infosys Limited | 64.34 | 71.46 | 23-Apr-2026 14:00 | No EPS decline |
| ACI | Archean Chemical Industries Limited | 13.12 | 8.65 | 11-May-2026 18:00 | EPS decline |
| AARTIIND | Aarti Industries Limited | 9.12 | 11.55 | 04-May-2026 14:00 | No EPS decline |

## Source verification

- **INFY:** NSE Integrated Filing identifies INFY as Main Board, FY ended 31-Mar-2026, audited consolidated results, board approval 23-Apr-2026 at 14:00; the FY2026 annual report gives consolidated diluted EPS 71.46 for FY2026 and 64.34 for FY2025. Sources: [NSE iXBRL filing](https://nsearchives.nseindia.com/corporate/ixbrl/INTEGRATED_FILING_INDAS_152465_23042026210154_iXBRL_WEB.html), [NSE FY2026 annual report](https://nsearchives.nseindia.com/annual_reports/AR_29297_INFY_2025_2026_A_8985010_29052026200926.pdf).
- **ACI:** NSE Integrated Filing identifies ACI as Main Board, audited consolidated results for FY ended 31-Mar-2026, board approval 11-May-2026 at 18:00; the annual report gives consolidated diluted EPS 8.65 for FY2026 and 13.12 for FY2025. Sources: [NSE iXBRL filing](https://nsearchives.nseindia.com/corporate/ixbrl/INTEGRATED_FILING_INDAS_156812_12052026023114_iXBRL_WEB.html), [NSE FY2026 annual report](https://nsearchives.nseindia.com/annual_reports/AR_29270_ACI_2025_2026_A_17400704_21052026210127.pdf).
- **AARTIIND:** NSE Integrated Filing identifies AARTIIND as Main Board, audited consolidated results for FY ended 31-Mar-2026, board approval 04-May-2026 at 14:00; the annual report gives consolidated diluted EPS 11.55 for FY2026 and 9.12 for FY2025. Sources: [NSE iXBRL filing](https://nsearchives.nseindia.com/corporate/ixbrl/INTEGRATED_FILING_INDAS_155487_04052026201324_iXBRL_WEB.html), [NSE FY2026 annual report](https://nsearchives.nseindia.com/annual_reports/AR_30737_AARTIIND_2025_2026_A_22486837_27082026184733.pdf).

## Interpretation guardrails

- Only ACI has an annual diluted EPS decline in this three-company sample; INFY and AARTIIND should exercise the `NO_EPS_DECLINE` path.
- EPS movement alone is not a price U-turn and is not evidence of a support level.
- Result approval date/time is retained to define the no-look-ahead boundary. The full announcement date is excluded from the 20-session peak window.
- No share-price peak, post-result close, proximity status, or trading signal is asserted yet.
- Corporate-action adjustment flags remain pending until the share capital/corporate action history is checked for the entire EPS and price comparison period.

## Next validation gate

For each symbol, retrieve exactly the 20 completed NSE sessions strictly before the result announcement calendar date, validate each daily High, select the maximum High, then retrieve the first/latest chosen completed post-result session Close under a documented rule. Check splits, bonuses, rights, ESOP dilution and other share-basis events. Only after this may `Peak_Price_Verified` and `Corporate_Action_Adjusted` be set true and the calculator run.


## 13. Session-date manifest

The 60-row manifest `research/ecms_uturn/nse_ohlc_download_manifest.csv` lists 20 expected NSE sessions for each issuer (INFY, AARTIIND, ACI), the official UDiFF archive URL for each date and the NSE holiday-calendar reference. The windows end on 22-Apr-2026, 30-Apr-2026 and 08-May-2026 respectively. The complete result announcement date is excluded for all issuers, including ACI's after-market 18:00 announcement on 11-May-2026.

These are expected calendar sessions, not proof that each archive file was downloaded or that each security row exists. Every row remains `EXPECTED_SESSION_PENDING_BHAVCOPY_VERIFICATION` until the actual NSE archive is read and its symbol/series/ISIN/High/Close fields are checked.


## Latest post-result close as-of snapshot

As of 17-Nov-2026 before the current session has completed, the latest completed session for all three issuers is expected to be 16-Nov-2026. The exact NSE UDiFF source URLs are recorded in `research/ecms_uturn/post_result_close_manifest.csv`. The close values are intentionally blank until each official daily bhavcopy is retrieved and its symbol/series/ISIN/close is checked. Do not use an intraday 17-Nov price.
