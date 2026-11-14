# ECMS — EOD Catalyst Momentum Scanner

An isolated strategy module inside AI-Trading-Bot. It does not modify or replace the existing NSE V8 production scanner.

## Objective
Find NSE Main Board stocks with unusual EOD volume, independently verify fundamental strength and fresh catalysts, then monitor those candidates during the next session. The morning Volume Gainers list is a confirmation source, not a mandatory eligibility gate.

## Two independent workflows
1. **ECMS EOD** — after market close: read the shared Bhavcopy/cache, identify unusual volume, enrich with fundamentals, verify the previous five calendar days of issuer-specific announcements/news, score candidates, and write an ECMS-only EOD report.
2. **ECMS Morning** — market session: load the latest completed ECMS EOD shortlist, obtain live NSE market data, compare live volume/price/liquidity and opening-range/VWAP behaviour, and produce a separate morning report. Start observation at 09:15 IST; do not make a final confirmation before 09:25–09:30 IST.

## Candidate policy
- Strong fundamentals and a strong, verified, price-relevant catalyst are primary eligibility requirements.
- Presence in the morning Volume Gainers list is optional. EOD-qualified candidates remain eligible for observation even if absent from that list.
- Absence from Volume Gainers is not itself a buy reason: price structure, liquidity, current market data and a defined invalidation level are still required.
- Never chase an extended gap-up. Record gap, opening range, VWAP, traded value, live relative volume and spread/liquidity where available.
- No broker orders, auto-buy, auto-sell or position execution.

## Data boundaries
- Shared existing data is read-only: data/bhavcopy/, data/cache/delivery/, data/cache/sector_index_daily/, data/cache/sector_constituents/, data/cache/sector_quote_classifications/, data/cache/universe/, data/inputs/sector_map.csv, data/inputs/sector_history.csv, data/inputs/fundamental_metrics.csv, data/cache/fundamental_history/, data/cache/telegram_premarket_news_seen.csv, data/cache/xbrl_samples/, data/cache/xbrl_period_pairs/, data/cache/shareholding_xbrl/, and outputs/v8_official_financial_results_filings.csv.
- These paths mirror the existing scanner's shared cache contract. Cache key/version and restore behaviour must be verified in both ECMS workflows; same path list alone is not proof that a cache was restored.
- ECMS writes only beneath outputs/ecms/ and its own strategy state beneath data/cache/ecms/. It must not write into or mutate shared production data.
- Existing .github/workflows/nse-test-scheduled.yml, scanner code and production outputs are out of scope and must remain untouched.

## Implementation gates
1. Build read-only data adapters and schema/coverage checks.
2. Add EOD volume/fundamental/catalyst stages and focused tests.
3. Add a live-market adapter only after a supported NSE source, terms/availability, timestamps and failure behaviour are verified.
4. Add the two workflows with separate schedules and ECMS-only output paths.
5. Run manual/shadow validation; only then enable schedules. A missing/stale feed must yield WAIT_FOR_DATA, never fabricated values.

## Initial scoring proposal (research-only; calibrate by backtest)
- Fundamentals: 30 points
- Catalyst strength and freshness: 30 points
- EOD/live volume and price action: 25 points
- Sector/market context: 15 points
The score is not a proven probability or a trading recommendation. Preserve component scores, evidence links, timestamps, source quality and missing-data status in every report.

## Output reports
- outputs/ecms/eod_candidates.csv
- outputs/ecms/eod_audit.csv
- outputs/ecms/morning_confirmation.csv
- outputs/ecms/morning_audit.csv

## Time handling
Use Asia/Kolkata. The EOD workflow must use the official NSE trading calendar and latest complete Bhavcopy session, not simply the machine date. Morning scan begins at 09:15 IST; final confirmation window begins no earlier than 09:25 IST.