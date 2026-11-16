# ECMS workflow contract — approved volume-origin research strategy

## Workflow and schedule

- Workflow file: `.github/workflows/ecms-volume-gainers-shadow.yml`.
- Regular-session EOD: daily schedule `30 11 * * *` UTC = **17:00 IST**.
- Regular-session Morning: daily schedule `50 3 * * *` UTC = **09:20 IST**.
- Special-session Morning can use a date-specific daily trigger slot (`14:25` IST for the configured 2026 Muhurat example); EOD remains at `17:00` IST after the special market close. The scanner checks the official calendar's date-specific expected time and skips mismatched clock slots.
- The official NSE Capital Market calendar is the session gate. Holidays/weekends skip; officially declared special sessions can run at their circular-defined times.
- Unknown/missing calendar coverage or a special session without an approved date-specific scan time must fail closed; never infer a trading day or session time from weekdays.
- When NSE publishes a special-session timing circular, add its Morning/EOD scan times to `data/inputs/nse_trading_calendar.json` and ensure matching UTC cron slots exist in the ECMS workflow before that session. The 2026 Muhurat cash-market circular specifies 14:20–15:30 IST; ECMS's configured scan slots are 14:25 IST for Morning and 17:00 IST for EOD.
- These triggers belong only to ECMS. Do not modify the production NSE V8 workflow or any unrelated workflow.
- The morning job restores the latest active EOD snapshot and ECMS fundamental workspace. After a successful prior-EOD comparison and persistence of the current Morning snapshot/report, it consumes the old active EOD reference. The current Morning snapshot remains for same-session EOD comparison. A valid same-session EOD then becomes the next trading session's active EOD reference.
- If Morning comparison/report persistence fails, the previous EOD reference remains available for retry. Holiday runs do not create or overwrite snapshots. EOD and morning artifacts/Telegram reports are separate.

## Universe and conditional fundamental gate

- Process eligible NSE Main Board equity rows returned by the NSE Volume Gainers page.
- Fundamentals may act as a rejection gate only when all applicable required metrics are complete, current, period/basis aligned and sufficiently verified. If data is incomplete, stale, conflicting or unverified, retain WAIT/PARTIAL status and continue other research; do not reject solely for missing data.
- Required applicable fundamental metrics: Revenue Growth, Profit Growth, ROE, ROCE, Debt/Equity, Interest Coverage and Operating Cash Flow, using the configured threshold file and approved sector applicability.
- Fundamental PASS/FAIL/WAIT remains a separate assessment. A verified fundamental FAIL may be rejected under approved sector-specific rules; WAIT/PARTIAL is not a pass, but it is not automatically rejected for missing evidence. Never force WAIT to PASS.
- RVOL, delivery/price behaviour, catalysts/news/events, valuation, bulk/block deals, sector context and technical evidence contribute to the later balanced research classification. They must not be used as unverified standalone rejection gates. Confirmed severe trap/surveillance risk may exclude only under the P5 evidence policy.

## Seven report information groups

1. Fundamentals and explicit PASS / FAIL / WAIT_FOR_DATA.
2. Issuer-matched company news from the last five calendar days, with official vs secondary source labels.
3. Confirmed upcoming company events, with date and source.
4. Next result date only when announced by issuer/exchange; otherwise `NOT ANNOUNCED`.
5. Indicative valuation label Cheap / Fair / Expensive from available P/E, PEG, P/B or EV/EBITDA multiples, with source/date/basis; otherwise `NOT AVAILABLE`. These are fixed, non-peer-adjusted information bands.
6. Latest 30-calendar-day NSE bulk and block deal disclosures for every eligible page stock: date, disclosed client/side, quantity, price and official exchange source. Informational only.
7. RVOL vs the previous 20 completed sessions' average volume, with value and data status. Informational only.

This list describes the earlier reporting baseline. The approved target strategy adds price/volume/delivery-origin analysis, sector/technical context and P5 evidence-backed trap exclusion. These layers become active only after implementation and phase evidence. Missing or unavailable data is never itself a rejection reason. Never infer an event, result date, valuation or deal when source evidence is absent.

## Morning repeat classification

- Reassess every eligible stock visible on the 09:20 NSE Volume Gainers page with the same fundamental-only rule. Include the EOD RVOL for context; do not compare partial-session morning volume with full-day RVOL.
- If a stock had Fundamental PASS in the saved EOD snapshot and appears again on the morning page, label it `EOD_FUNDAMENTAL_PASS_REPEAT`.
- Distinguish that from `NEW_MORNING_ENTRY`, `EOD_ONLY_NOT_ON_MORNING_PAGE`, and `MORNING_FUNDAMENTAL_FAIL` / `MORNING_WAIT_FOR_DATA`.
- Repeat/new/disappeared labels remain page-presence context only and do not independently change fundamental status or create a separate rejection rule.

## Sources and quality

- Official NSE XBRL/issuer filings are primary; BSE official filings are official cross-checks.
- Screener.in free public observations may be entered manually. No Premium export, paid API, login automation or scraping.
- Yahoo Finance/yfinance is third-party comparison data, not official verification.
- Keep metric-level source, URL, period, publication date, basis and unit. Never average conflicts or upgrade manual/provider data to official verification.
- Apply approved financial-sector metric applicability for banks/NBFCs/insurers.
- Non-fundamental missing values are `NOT AVAILABLE` / `NOT ANNOUNCED`; they do not alter the fundamental status.

## Isolation and safety

- Shared production inputs/cache are read-only.
- ECMS state/cache stays under `data/cache/ecms/`; reports stay under `outputs/ecms/`.
- No edits to `.github/workflows/nse-test-scheduled.yml`, NSE V8, shared providers, production scanner, shared thresholds or unrelated workflows.
- Research/shadow-only. No broker integration, order placement, auto-buy or auto-sell.


## Approved strategy decisions and P0–P8 roadmap (16-Nov-2026)

The current target strategy and phase order are defined in [ECMS README — Approved ECMS strategy and execution roadmap](README.md#approved-ecms-strategy-and-execution-roadmap--16-nov-2026). That section is the ECMS decision record and supersedes older fundamental-only wording in this contract.

- Objective: identify whether NSE Volume Gainer volume has positive demand/accumulation evidence, negative selling/distribution evidence, a genuine event catalyst or suspicious/high-risk evidence. A Volume Gainer is a research candidate, not a buy signal; profit is not guaranteed.
- Process every eligible Main Board stock returned by the NSE Volume Gainers page; no Top-N cap on eligible page rows.
- No basket construction and no historical backtesting. P8 means live Morning/EOD shadow-output, cache, report, Telegram, coverage and runtime verification only.
- Collect fundamentals for every eligible page stock. Complete, current, applicable and verified fundamentals may use the approved fundamental rejection rules. Incomplete/unverified fundamentals remain WAIT/PARTIAL and must not alone reject; continue the remaining research layers without calling the stock fundamentally strong.
- Positive/negative volume-origin classification must combine price, volume, delivery and follow-through with company disclosures and other available evidence. High delivery alone does not prove accumulation; missing data does not prove negative activity or a clean bill of health.
- Trap handling is EXCLUDE only for severe risk supported by a validated rule or corroborated evidence. Preserve a separate evidence-backed exclusion ledger.
- Work strictly P0 → P1 → P2 → P3 → P4 → P5 → P6 → P7 → P8. Do not change the two-scan schedule or production NSE V8 boundaries.
