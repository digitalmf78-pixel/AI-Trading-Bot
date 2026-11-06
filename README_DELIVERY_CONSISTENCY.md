# Delivery Consistency Intelligence

This is an observational report only. It does not change the existing five-session Delivery Category A/B gate, RVOL, liquidity, fundamental, technical, ranking, or watchlist eligibility.

## Windows and classification

The module reads the latest 20 distinct valid NSE delivery reports on or before the EOD date. It retains the real report dates and never relabels an older report as current-day data.

For each 5-, 10-, and 20-session window:

- Category A: arithmetic average Delivery % is >= 60.00% (inclusive).
- Category B: every session's Delivery % is >= 60.00% (inclusive).
- If a symbol is missing a valid value in any session in that window, that window's A/B status is WAIT_FOR_DATA.

The original scanner's 5D Category A/B fields remain authoritative and unchanged. The consistency module writes separate fields prefixed with Delivery5D, Delivery10D, and Delivery20D.

## 20-session consistency tag

Tags use the count of daily observations >= 60% across the complete 20-session window:

- VERY_HIGH_CONSISTENCY: 20/20
- HIGH_CONSISTENCY: 18-19/20
- CONSISTENT: 14-17/20
- NORMAL: 0-13/20
- WAIT_FOR_DATA: fewer than 20 valid observations

Delivery20DCurrentStreak counts uninterrupted >=60% delivery observations backward from the latest report date.

## Outputs

outputs/v8_delivery_consistency_YYYYMMDD.csv

The module is integrated as a sidecar after the existing 5D delivery audit. If 20-session history cannot be collected or validated, it writes WAIT_FOR_DATA observations and the original 5D pipeline continues unchanged.
