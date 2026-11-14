# ECMS workflow contract — EOD phase

## Workflow A — ECMS EOD (implemented; manual only)
- Trigger: `workflow_dispatch` only. No cron schedule yet.
- Restore the same ordered shared-cache path list as the production scanner, using compatible branch/main restore prefixes.
- Read Bhavcopy, fundamental metrics, official filing metadata, XBRL evidence and board-list caches without modifying them.
- Require the latest complete Bhavcopy to equal the latest completed NSE session according to the official calendar.
- Require 20 prior complete sessions; calculate RVOL against the prior 20-session average. Initial threshold: RVOL >= 1.5.
- Apply the same listed-equity series and official NSE Main Board / SME exclusion policy as the existing scanner.
- Verify fundamentals with the existing metric-level XBRL verifier using local cached evidence only. No XBRL fetch is allowed in this isolated phase.
- Check the trailing five calendar days for issuer-matched NSE announcements and secondary news. Source unavailability must not be described as no news.
- Use conservative catalyst keyword triage and expose all matched headlines/risk flags for human review.
- Write only beneath `outputs/ecms/`. Do not mutate shared cache, shared metrics, filing register or evidence ledger.

## Workflow B — ECMS Morning (not implemented)
- Do not create or schedule it in this phase.
- Later, obtain live market data from a verified provider/endpoint. Do not assume the NSE Volume Gainers web page is a stable API.
- Track EOD candidates whether or not they appear in the live Volume Gainers ranking.
- Capture timestamp, LTP, open, previous close, volume, traded value, relative volume, VWAP (if reliable), opening range and data freshness.
- No final confirmation before 09:25–09:30 IST; no order placement.

## Shared cache contract
The EOD workflow restores the same ordered cache path list as the production scanner, with a unique run key and compatible restore prefixes for branch and main. It logs cache-hit and matched-key outputs. Required files and freshness are checked by the EOD module. Cache restore is not considered proof that every required file is present.

## Operational safety
- Manual/shadow-only until unit tests pass and the first artifact is reviewed.
- A feed failure, empty response, HTML challenge, stale data, symbol mismatch, missing filing or incomplete XBRL evidence must result in `WAIT_FOR_DATA` or an explicit failure.
- No broker integration, order placement, auto-buy or auto-sell.
- Never alter `.github/workflows/nse-test-scheduled.yml`, existing production scanner logic or shared cache contents.
