# HDFC Bank — Gemini Exact-Date Trade Log Verification

**Status: REJECTED AS PROVIDED — supplied prices do not match the historical market tape.**  
**Scope:** read-only historical price verification; no production/cache changes.

## Gemini claim

- Peak: 17-Jul-2023, ₹1,720
- Entry: 18-Oct-2023, ₹1,675; delivery 74.5%; RVOL 1.7x
- Exit: 15-Dec-2023, ₹1,880
- Claimed return: +12.2%

## Historical price evidence

A historical daily OHLC series gives:

| Date | Close | Open | High | Low |
|---|---:|---:|---:|---:|
| 18-Oct-2023 | ₹1,519.75 | ₹1,541.20 | ₹1,541.20 | ₹1,518.10 |
| 15-Dec-2023 | ₹1,656.56 | ₹1,650.00 | ₹1,668.00 | ₹1,646.60 |

The 18-Oct row is also independently corroborated by EquityPandit's historical table in a 1:2 bonus-adjusted presentation: close ₹759.88, open/high ₹770.60, low ₹759.05. Multiplying by two restores the pre-bonus price basis: close ₹1,519.76, high ₹1,541.20.

The 15-Dec EquityPandit row is close ₹828.28, open ₹825.00, high ₹834.00, low ₹823.30; multiplied by two this is close ₹1,656.56 and high ₹1,668.00.

HDFC Bank later issued a 1:1 bonus with ex-date 26-Aug-2025. Any historical comparison must state whether prices are raw pre-bonus or adjusted post-bonus. This adjustment does not reconcile the Gemini prices: on 18-Oct-2023 the reported high was ₹1,541.20, not ₹1,675; on 15-Dec-2023 the reported high was ₹1,668, not ₹1,880.

Sources:
- Historical daily OHLC, Oct 2023: https://www.equitypandit.com/hdfc-bank-outlook-for-the-week-october-23-2023-october-27-2023/
- Historical daily OHLC, 18-Oct and 15-Dec 2023: https://www.equitypandit.com/historical-data/HDFCBANK
- Raw-price cross-check for Oct 2023: https://id.scribd.com/document/904283246/HDFC-Stock-Price-Market-Performance-Trend
- HDFC Bank official 1:1 bonus announcement / allotment: https://www.sec.gov/Archives/edgar/data/1144967/000119312525191696/d22509dex99.htm
- NSE corporate-action reference (1:1 bonus, ex-date 26-Aug-2025): https://nsearchives.nseindia.com/content/circulars/FAOP69840.pdf

## Arithmetic and verdict

The arithmetic on the supplied entry and exit values is correct:
(₹1,880 / ₹1,675 − 1) × 100 = +12.24%.

But the trade is **not historically executable on the supplied dates**:
- ₹1,675 entry is ₹133.80 above the reported 18-Oct daily high of ₹1,541.20.
- ₹1,880 exit is ₹212 above the reported 15-Dec daily high of ₹1,668.
- Thus neither claimed transaction price was reached on its stated date.

The observed close-to-close move from 18-Oct to 15-Dec on the raw pre-bonus basis is approximately +9.00% (₹1,519.75 → ₹1,656.56). This is not the claimed trade and does not validate the U-Turn formula.

## Still unverified

- Delivery percentage 74.5% on 18-Oct-2023.
- RVOL 1.7x, including its lookback definition and whether current session is excluded.
- Correct result-announcement date and annual diluted EPS periods used in the U-Turn calculation.
- Whether the ₹1,720 peak and ₹1,670 target were quoted on a raw pre-bonus basis and calculated from the approved annual diluted EPS formula.

**Research decision:** do not count this as a win. Request Gemini's raw source rows / original export for the OHLC and the delivery/RVOL calculations. The exact-date price contradiction is enough to invalidate the claimed +12.2% trade as currently documented.
