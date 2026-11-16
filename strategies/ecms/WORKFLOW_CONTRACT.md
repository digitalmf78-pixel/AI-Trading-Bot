# ECMS workflow contract — fundamental-only gate

## Workflow and schedule

- Workflow file: `.github/workflows/ecms-volume-gainers-shadow.yml`.
- EOD job: daily schedule `30 11 * * *` UTC = **17:00 IST**; manual dispatch with mode `eod`.
- Morning job: daily schedule `50 3 * * *` UTC = **09:20 IST**; manual dispatch with mode `morning`.
- Daily triggers are intentional: the official NSE Capital Market calendar is the session gate, so holidays/weekends skip while officially declared special sessions (including Saturday sessions) can run.
- Unknown/missing calendar coverage must fail closed; never infer a trading day from weekdays.
- These triggers belong only to ECMS. Do not modify the production NSE V8 workflow or any unrelated workflow.
- The morning job restores the latest active EOD snapshot and ECMS fundamental workspace. After a successful prior-EOD comparison and persistence of the current Morning snapshot/report, it consumes the old active EOD reference. The current Morning snapshot remains for same-session EOD comparison. A valid same-session EOD then becomes the next trading session's active EOD reference.
- If Morning comparison/report persistence fails, the previous EOD reference remains available for retry. Holiday runs do not create or overwrite snapshots. EOD and morning artifacts/Telegram reports are separate.

## Universe and sole rejection rule

- Process eligible NSE Main Board equity rows returned by the NSE Volume Gainers page.
- **Fundamental assessment is the only stock rejection filter.**
- Required applicable fundamental metrics: Revenue Growth, Profit Growth, ROE, ROCE, Debt/Equity, Interest Coverage and Operating Cash Flow, using the configured threshold file and approved sector applicability.
- Fundamental PASS is the only status that includes a stock in the fundamental-pass set. Fundamental FAIL is rejected. Missing/stale/conflicting/unverified required fundamental evidence is `WAIT_FOR_DATA`; never force it to PASS.
- Do not add RVOL, catalyst/news sentiment, upcoming events/results, valuation, bulk/block deals, research score/grade, coverage percentage, sector momentum or technical conditions as rejection, ranking-gate or suppression rules.

## Seven report information groups

1. Fundamentals and explicit PASS / FAIL / WAIT_FOR_DATA.
2. Issuer-matched company news from the last five calendar days, with official vs secondary source labels.
3. Confirmed upcoming company events, with date and source.
4. Next result date only when announced by issuer/exchange; otherwise `NOT ANNOUNCED`.
5. Indicative valuation label Cheap / Fair / Expensive from available P/E, PEG, P/B or EV/EBITDA multiples, with source/date/basis; otherwise `NOT AVAILABLE`. These are fixed, non-peer-adjusted information bands.
6. Latest 30-calendar-day NSE bulk and block deal disclosures for fundamental-PASS stocks: date, disclosed client/side, quantity, price and official exchange source. Informational only.
7. RVOL vs the previous 20 completed sessions' average volume, with value and data status. Informational only.

All groups except fundamentals are informational. Their positive, negative or unavailable status cannot reject a fundamental-PASS stock. Never infer an event, result date, valuation or deal when source evidence is absent.

## Morning repeat classification

- Reassess every eligible stock visible on the 09:20 NSE Volume Gainers page with the same fundamental-only rule. Include the EOD RVOL for context; do not compare partial-session morning volume with full-day RVOL.
- If a stock had Fundamental PASS in the saved EOD snapshot and appears again on the morning page, label it `EOD_FUNDAMENTAL_PASS_REPEAT`.
- Distinguish that from `NEW_MORNING_ENTRY`, `EOD_ONLY_NOT_ON_MORNING_PAGE`, and `MORNING_FUNDAMENTAL_FAIL` / `MORNING_WAIT_FOR_DATA`.
- Repeat/new/disappeared labels are informational and do not create a second rejection rule.

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
