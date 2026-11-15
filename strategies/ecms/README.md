# ECMS — NSE Volume Gainers Research

ECMS is an isolated, research-only workflow for stocks appearing on the NSE Volume Gainers page. It does not place orders and must not change or depend on the production NSE V8 scanner.

## Exact ECMS scope

For each eligible NSE Volume Gainer, publish only these seven information groups:

1. **Fundamentals (the only rejection filter):** Revenue Growth, Profit Growth, ROE, ROCE, Debt/Equity, Interest Coverage and Operating Cash Flow. Apply the configured fundamental thresholds and sector-specific applicability. A stock is included in the fundamental-pass set only when the required applicable fundamental checks pass. Missing or unverified required fundamental data is `WAIT_FOR_DATA`, not a pass.
2. **Last five days' company news:** issuer-matched news/announcements, with official and secondary sources clearly distinguished.
3. **Upcoming company events:** only explicitly announced/confirmed NSE event-calendar entries within the next 90 calendar days, with date and source.
4. **Upcoming result:** next result date only when announced by the company/exchange; otherwise `NOT ANNOUNCED`.
5. **Valuation:** Indicative Cheap / Fair / Expensive from available P/E, PEG, P/B or EV/EBITDA multiples, with source, as-of date and basis shown; otherwise `NOT AVAILABLE`. These fixed multiple bands are not peer-adjusted and share price alone is not valuation.
6. **Bulk deals / Block deals:** NSE exchange-disclosed deals over the latest 30 calendar days, including deal date, client name/side, quantity and price. Show this information for fundamental-PASS stocks; it is informational and never a rejection condition.
7. **RVOL:** current volume relative to the prior 20 completed sessions' average volume. Display the value and data status; RVOL is informational only and never a rejection condition.

**No non-fundamental field may reject, qualify, rank-gate or suppress a stock.** News sentiment, upcoming events/results, valuation, bulk/block deals and RVOL are context only. Missing context is shown as `NOT AVAILABLE` and does not reject a fundamental-PASS stock. Do not add technical, sector, catalyst, volume or research-score rejection gates.

## Daily checkpoints (Asia/Kolkata)

- **EOD:** weekday schedule at **16:45 IST**. Read the completed NSE Volume Gainers page, calculate/display 20-session RVOL, assess fundamentals, and collect the information groups above. Save the EOD symbol/fundamental snapshot in ECMS-owned state.
- **Morning:** weekday schedule at **09:20 IST**. Re-read the current NSE Volume Gainers page and reassess current-page stocks using the same fundamental-only gate.
- **Morning repeat marking:** if a stock that passed fundamentals at EOD appears again on the 09:20 page, mark it explicitly as `EOD_FUNDAMENTAL_PASS_REPEAT` (separate from a new morning entry). Also retain clear labels for new entries, EOD names no longer present, and morning fundamental status. A repeat label is informational, not an extra filter.
- EOD and morning reports/Telegram messages remain separate. The morning run must restore the previous EOD snapshot and ECMS fundamental workspace.

GitHub Actions cron values are UTC: `15 11 * * 1-5` = 16:45 IST and `50 3 * * 1-5` = 09:20 IST. These schedules belong only to `.github/workflows/ecms-volume-gainers-shadow.yml`.

## Fundamental data quality and sources

- Prefer official NSE XBRL / issuer filings; use official BSE filings as an official cross-check where available.
- Free Screener.in observations may be manually captured from publicly visible pages. No Screener Premium, paid API, login automation or scraping.
- Yahoo Finance/yfinance is third-party comparison data, never described as official verification.
- Preserve metric-level source, URL, financial period, publication date, calculation basis and unit. Do not average conflicting sources or silently promote provider/manual observations to official verification.
- For banks/NBFCs/insurers, mark metrics that are not applicable under the approved sector treatment; do not force industrial-company ratios onto financial institutions.
- Missing, stale, conflicting or unverified required fundamental evidence remains `WAIT_FOR_DATA`. Never manufacture a pass.
- For non-fundamental information, distinguish `NOT AVAILABLE`, `NOT ANNOUNCED` and source-unavailable states; these do not change the fundamental result.

## ECMS isolation

- Shared NSE inputs and production caches are read-only.
- ECMS-owned state/cache stays under `data/cache/ecms/`; reports stay under `outputs/ecms/`.
- Do not modify `.github/workflows/nse-test-scheduled.yml`, NSE V8, shared provider behavior, shared thresholds, production scanner logic or unrelated workflows.
- No broker integration, order placement, auto-buy or auto-sell.

## Current implementation / delivery status

The EOD and 09:20 workflow jobs and schedules are present in `.github/workflows/ecms-volume-gainers-shadow.yml`. The ECMS implementation uses the fundamental shortlist as the sole decision gate, marks EOD fundamental-PASS repeats in the morning report, and adds informational enrichment for five-day news, the NSE event calendar, result dates, indicative valuation and official NSE bulk/block deal disclosures. Morning RVOL is deliberately shown as unavailable because a partial 09:20 session is not comparable with a full-day 20-session average; the prior EOD RVOL is retained for reference. The zero-Fundamental-PASS enrichment crash fix and regression test were merged in PR #123. A fresh live EOD/morning run is still required to verify real-source behavior.


## External repository reference audit — 2026-11-15

Reviewed public reference repository: [vinay123kum/nse-stock-screener](https://github.com/vinay123kum/nse-stock-screener).

### What the reference implementation does

- Reads the NSE equity symbol list from local CSV files (`EQUITY_L.csv` and `total.csv`).
- Fetches Screener.in consolidated company pages, falls back to standalone when consolidated statements are empty, and parses the visible profit-and-loss, balance-sheet, cash-flow, quarterly and shareholding tables.
- Stores one JSON cache file per symbol and skips symbols already cached, allowing a run to resume after interruption.
- Uses retry/backoff for HTTP 429 and transient request failures.
- Separates data fetching, screening, ranking and HTML report generation into `fetch.py`, `screen.py`, `rank.py` and `report.py`.

### ECMS reuse decision

**Do not copy or execute the reference `fetch.py` in ECMS.** It automatically scrapes Screener.in, which conflicts with the ECMS source policy in this README (manual free-page observations only; no scraping, login automation or Premium access). Its market-cap/fall/debt/FCF filters and percentile ranking are also unrelated to ECMS's required fundamental-only decision gate and must not be imported.

Potentially reusable engineering patterns, subject to ECMS-specific tests:

1. Per-symbol resumable cache/state so a failed run does not unnecessarily refetch every completed symbol.
2. Explicit consolidated-versus-standalone basis tracking; never silently mix the two.
3. Retry/backoff and per-symbol error records for transient source failures.
4. Keep fetch/parse/assessment/report stages separate and retain raw source evidence alongside normalized values.

### Important limitations found

- The repository is a small local Python script pipeline (`requests`, `BeautifulSoup`); its README instructs the user to run scripts locally.
- The inspected root contains no GitHub Actions workflow, web-server entry point, Dockerfile, Procfile, or hosted deployment configuration. It is not a ready-to-deploy hosted application based on the files inspected.
- Screener.in values are scraped observations, not exchange-verified XBRL facts. The code extracts a subset of visible fields and does not establish official filing provenance or metric-level verification.
- Consolidated-to-standalone fallback is useful for coverage, but the resulting basis must remain visible in every metric audit.

**Conclusion:** Use this repository only as an engineering reference for resumability, retries, source-basis labeling and pipeline separation. Do not adopt its scraper, filters, ranking logic or data as official fundamental evidence. No external code or data provider has been added to ECMS by this audit.
