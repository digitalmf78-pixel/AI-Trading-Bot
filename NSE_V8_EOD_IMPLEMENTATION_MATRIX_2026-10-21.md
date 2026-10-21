# EOD System Specification — Implementation Matrix

| User step | Patch status | Evidence / caveat |
|---|---|---|
| 1. Official NSE Main Board universe | Preserved | Existing official board filter and audit remain in place. |
| 2. Validate symbols/security types | Preserved | Existing symbol/security-series and ETF handling remains in place. |
| 3. Latest valid EOD data | Preserved | Existing retrieval/cache fallback remains; latest supplied run used 2026-10-19 after 404s for 20/21 Oct. |
| 4. Five-session Delivery >=60% each day | Preserved | Existing per-session threshold is authoritative; missing history => WAIT_FOR_DATA. |
| 5. 20-session liquidity | Reordered to match latest spec | Remains >=₹5 crore average daily traded value; missing history => WAIT_FOR_DATA. |
| 6. Fundamental strength | New hard gate | Supports the requested metrics, source provenance, and explicit thresholds. No financial source connector is yet automated; absent data/config => WAIT_FOR_DATA. |
| 7. Sector mapping/strength | Preserved | Existing sector module is still used; missing evidence is not guessed. |
| 8. News/corporate announcements | Preserved | Existing news/catalyst and upcoming-event logic remains in place. |
| 9. Technical analysis | Preserved | Existing trend, RVOL, price-volume, CLV, breakout/pullback, support/resistance and relative-strength logic remains. |
| 10. Candidate score | Gate enforced | RVOL/technical ranking occurs only after Delivery, Liquidity and Fundamental PASS; final promotion also requires later gates. |
| 11. Market and portfolio risk | Extended | Existing market regime/RR/chase checks preserved; explicit portfolio risk/position sizing module added. Requires verified risk config and current exposure values. |
| 12. Final shortlist max 4 | Implemented | `outputs/v8_final_shortlist.csv`, capped at four eligible rows. |
| 13. Required reports | Implemented/Preserved | Fundamental, risk, technical, stage-status, passed, rejected, wait, existing sector/news, and final shortlist reports. |
| 14. Regression tests | Added to workflow | New fundamental/risk/pipeline tests plus existing V8 regression suites. |
