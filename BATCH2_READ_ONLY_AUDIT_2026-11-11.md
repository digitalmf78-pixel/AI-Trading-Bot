# Batch 2 — Read-only audit report

**Audit date:** 2026-11-11  
**Repository:** `digitalmf78-pixel/AI-Trading-Bot`  
**Baseline EOD date:** 2026-11-09  
**Baseline workflow run:** `42634890331`  
**Baseline commit:** `5346f893603ac2edfa519ee869bc61176c44fdb1`  
**Artifact:** `nse-v8-reports-42634890331` (downloaded and inspected)

## A. Track 1 funnel — observed baseline evidence

The archived 2026-11-09 artifact supports these counts:

| Stage | Observed count |
|---|---:|
| Official Mainboard PASS | 2,588 |
| Delivery A OR B union PASS | 758 |
| Delivery category A only | 656 |
| Delivery A AND B overlap | 102 |
| Delivery B only | 0 |
| Liquidity PASS | 54 |
| Core Technical PASS | 3 |
| Final EOD WATCH | 0 |
| Final EOD SKIP | 52 |
| Final EOD WAIT_FOR_DATA | 2 |

Evidence files:
- `outputs/v8_main_board_universe_audit.csv`: 2,588 `PASS_MAIN_BOARD`, 449 `EXCLUDED_SME`.
- `outputs/v8_delivery_dual_category_audit.csv`: 758 `PASS_A_OR_B`, 1,615 `FILTERED_OUT_A_AND_B`, 215 `WAIT_FOR_DATA`; `DeliveryCategory` gives 656 `A_ONLY`, 102 `A_AND_B`, no `B_ONLY`.
- `outputs/v8_liquidity_first_audit.csv`: 54 `PASS`, 661 `FILTERED_OUT_BELOW_MINIMUM`, 43 `WAIT_FOR_DATA`.
- `outputs/v8_technical_report.csv`: 3 `CoreTechnicalScreenStatus=PASS`, 51 `REJECT`.
- `outputs/v8_eod_watchlist.csv`: 0 `WATCH`, 52 `SKIP`, 2 `WAIT_FOR_DATA`.

**After-change parity:** not yet run. The counts above are verified baseline evidence only; they are not represented as post-change results. The PR's CI tests and a same-input replay are required before parity can be certified.

## B. NSE delivery archive depth — not verified

The official NSE All Reports page lists **Full Bhavcopy and Security Deliverable data** with a date selector. The separate Security-wise Archives page shows 1D/1W/1M/3M/6M/1Y/5Y/Custom choices, but that page is labelled Security-wise Price Volume Archives; this does not by itself prove the same retention depth for the daily Security Deliverable report.

Attempts to open the four dated `sec_bhavdata_full_YYYYMMDD.csv` archive URLs through this research channel were inaccessible; that is not an HTTP 404/403 result and does not establish that NSE lacks the files. Therefore **30/60/90/130-day archive availability is verify nahi zale**.

### Exact manual check
On the official NSE website:
1. Open **All Reports → Equities**.
2. Select **Full Bhavcopy and Security Deliverable data**.
3. Set the report date and download the file for each date below.
4. Confirm that the file opens, has the expected date, and contains the delivery quantity and delivery percentage fields used by the scanner. Record the exact filename, HTTP/download result, row count, and SHA-256.
5. If a date is unavailable, repeat through the Security-wise Archives **Custom** range only as a separate test; verify that the downloaded report actually contains delivery fields before treating it as a substitute.

| Calendar lookback from 2026-11-11 | Date to test |
|---|---|
| 30 days | 2026-10-12 |
| 60 days | 2026-09-11 |
| 90 days | 2026-08-13 |
| 130 days | 2026-07-03 |

No delivery archive limit should be coded or assumed until these files have been checked.

## C. NSE 2027 holiday calendar

The repository calendar currently covers 2025 and 2026 only. The official NSE Market Timings & Holidays page, checked on 2026-11-11, displays the 2026 Equities holiday list; a 2027 Equities holiday list was not visible there. **No 2027 holidays or special sessions have been added or guessed.**

The scanner's calendar coverage warning starts in November when the following year is missing, and an unconfigured year fails closed. Therefore:
- Recommended update window: as soon as NSE publishes the official 2027 Capital Market–Equities holiday notice; complete review before 2026-12-31.
- Hard operational deadline: before the first 2027 scan, because 2027-01-01 onward will fail closed until the year is configured.

### Manual update steps after official publication
1. Open NSE **Market Timings & Holidays** and select the **Capital Market – Equities** segment and year 2027.
2. Obtain the official NSE holiday notice/circular. Record only the published dates and descriptions.
3. Update `data/inputs/nse_trading_calendar.json` under `years.2027.holidays`; add special sessions only when an official NSE circular confirms them.
4. Do not infer Muhurat or other special-session dates from a festival calendar.
5. Run the calendar unit tests and inspect `calendar_coverage_warnings()` for a date in 2027 before enabling 2027 scanner runs.

## Official sources
- NSE All Reports (Equities; Full Bhavcopy and Security Deliverable data): https://www.nseindia.com/all-reports
- NSE Historical Reports — Capital Market: https://www.nseindia.com/static/resources/historical-reports-capital-market-daily-monthly-archives
- NSE Market Timings & Holidays: https://www.nseindia.com/resources/exchange-communication-holidays
