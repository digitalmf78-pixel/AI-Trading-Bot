# U-Turn Pilot — Official NSE Calendar and Event-Time Audit

**Audit date:** 17-Nov-2026  
**Scope:** INFY, ACI and AARTIIND pilot only; isolated research branch; shared NSE V8 cache read-only.

## 1. Official NSE 2026 equity calendar

Source: [NSE Capital Market Segment Circular NSE/CMTR/71775, 12-Dec-2025](https://archives.nseindia.com/content/circulars/CMTR71775.pdf) and [NSE market holidays page](https://www.nseindia.in/resources/exchange-communication-holidays).

The three manifest windows were independently rebuilt as all weekdays between each window's start/end, excluding official NSE 2026 equity holidays. Each result exactly matches the manifest's 20 dates:

| Symbol | 20-session window | Calendar result | Cache OHLC rows |
|---|---|---|---:|
| INFY | 20-Mar-2026 to 22-Apr-2026 | PASS, exact 20/20 | 20/20 |
| ACI | 09-Apr-2026 to 08-May-2026 | PASS, exact 20/20 | 20/20 |
| AARTIIND | 01-Apr-2026 to 30-Apr-2026 | PASS, exact 20/20 | 20/20 |

The date lists exclude 26-Mar, 31-Mar, 03-Apr, 14-Apr and 01-May where applicable. 01-Apr-2026 is an equity trading session; the bank annual closing day is not an NSE equity holiday. The independent validator also compares the strict parser's 20 verified symbol rows against the event-study parser's peak date and peak High.

## 2. Result event timing

| Symbol | Event date used | Official timing evidence | First post-result session |
|---|---|---|---|
| INFY | 23-Apr-2026 | Infosys scheduled earnings release around 15:45 IST; NSE board outcome file timestamp 17:00:27 | 24-Apr-2026 |
| ACI | 11-May-2026 | Board meeting ran 18:00–21:30 IST; outcome PDF is dated 11-May and NSE archive filename carries 12-May 00:30:06. Exact public release minute is not independently established. | 12-May-2026 |
| AARTIIND | 04-May-2026 | NSE board-outcome PDF timestamp 18:12:40; company secretary digital signature 18:04:55 | 05-May-2026 |

Sources:
- INFY: [Infosys official release schedule](https://www.infosys.com/newsroom/press-releases/documents/2026/q4-apr23-2026.pdf), [NSE board outcome](https://nsearchives.nseindia.com/corporate/Infosys_23042026170027_outcome.pdf).
- ACI: [NSE board outcome](https://nsearchives.nseindia.com/corporate/ARCHEAN_12052026003006_BoardMeetingOutcome.pdf), [NSE integrated filing](https://nsearchives.nseindia.com/corporate/ixbrl/INTEGRATED_FILING_INDAS_156812_12052026023114_iXBRL_WEB.html).
- AARTIIND: [NSE board outcome](https://nsearchives.nseindia.com/corporate/AARTIIND_04052026181240_Outcomemarch.pdf), [issuer press release](https://www.aarti-industries.com/press-releases/Press-Release-Q4-FY-26).

Event dates are the dated board-result announcements. The first post-result session is the next NSE equity session. ACI's exact public release minute remains explicitly unverified; no invented 14:00 timestamp is retained.

## 3. Corporate actions and dividend handling

No bonus, split, rights issue or demerger was found in the reviewed event windows. Cash dividends are separately recorded and added to a second, gross no-reinvestment horizon estimate. The raw price-only returns remain available and are not silently altered.

| Symbol | Cash dividend ex-date | Amount/share | Record date |
|---|---|---:|---|
| INFY | 10-Jun-2026 | ₹25.00 | 10-Jun-2026 |
| INFY | 03-Nov-2026 | ₹26.00 | 03-Nov-2026 |
| ACI | 04-Jun-2026 | ₹2.50 | 05-Jun-2026 |
| AARTIIND | 11-Sep-2026 | ₹1.00 | 14-Sep-2026 |

Sources:
- INFY: [NSE corporate actions](https://www.nseindia.com/companies-listing/corporate-filings-actions?symbol=INFY&tabIndex=equity), [Infosys interim dividend board outcome](https://archives.nseindia.com/corporate/Infosys_23102026160704_BM_Outcome_Oct232026_1.pdf).
- ACI: [NSE record-date filing](https://nsearchives.nseindia.com/corporate/ARCHEAN_12052026010551_Record_Date_Intimation.pdf), [MSE corporate action listing](https://www.msei.in/corporates/corporate-securities-information/corporate-update/default?symbol=ACI&type=4&vmode=vm), [FY26 annual report](https://www.archeanchemicals.com/investor-relations/admin/assets/products/ACIL%20Annual%20Report%2025-26.pdf).
- AARTIIND: [NSE quote / corporate actions](https://www.nseindia.in/get-quote/equity/AARTIIND/Aarti-Industries-Ltd), [FY26 annual report](https://nsearchives.nseindia.com/annual_reports/AR_30737_AARTIIND_2025_2026_A_22486837_27082026184733.pdf).

Dividend-inclusive figures are a simple gross cash-added estimate: (end close + cash dividends whose ex-date falls after start and on/before end − start close) / start close. No dividend reinvestment, tax, fees, or official total-return index is modeled.

## 4. Validation result and limitations

- Same-run strict cache/event-study consistency gate: PASS.
- Official NSE calendar comparison: PASS, all three 20-session windows exact.
- Strict OHLC cache rows: 60/60 READY.
- Latest post-result close rows: 3/3 READY.
- Delivery rows: 60/60 matched in the pilot windows.
- Corporate-action review: no stock-action adjustment found; cash dividends listed separately.
- EPS values: official consolidated annual diluted EPS source pairs recorded for all three pilot names.
- This remains a **three-stock descriptive pilot, not a randomized or statistically representative study**. Only ACI has an EPS decline. No entry, exit, P&L, fees, slippage or trade simulation was performed. Cash-dividend simple returns are not a full total-return index.

Machine-readable checks: `v8_cache_audit/official_calendar_corporate_action_audit.json` in the latest U-Turn CI artifact.
