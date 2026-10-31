# NSE V8 P2 — Quarterly TTM Fundamental Calculation

## आधार
हा patch user ने दिलेल्या `AI-Trading-Bot-main (16).zip` या repository snapshot वर आधारित आहे. P1 cache-basis/provenance fields कायम ठेवले आहेत. Master specification, Delivery A/B, RVOL, Liquidity, technical filters, shortlist thresholds आणि 30-day refresh policy बदललेली नाही.

## काय जोडले
- Quarterly income, cash-flow आणि balance-sheet statements मधील period-end alignment.
- Latest 4 consecutive quarters वर Revenue TTM, Net Profit TTM, EBIT TTM, Interest Expense TTM आणि Operating Cash Flow TTM.
- Revenue/Profit Growth साठी latest 4 quarters विरुद्ध आधीचे 4 quarters (एकूण 8 consecutive income quarters).
- ROE/ROCE साठी current quarter आणि चार quarter आधीचा Balance Sheet वापरून average equity/capital employed.
- Debt/Equity latest aligned balance sheet वर.
- Interest Coverage TTM EBIT / TTM interest expense.
- FCF TTM reported Free Cash Flow उपलब्ध असल्यास; अन्यथा चार तिमाही OCF + CapEx.
- TTM audit columns fundamental report मध्ये pass-through.
- Quarterly TTM unavailable असल्यास आधीचा aligned annual method fallback म्हणून कायम.
- Quarterly TTM path मध्ये Yahoo `info` snapshot values मिसळले जात नाहीत.

## Fail-closed नियम
- 4 consecutive quarterly income periods नसतील तर quarterly TTM वापरला जात नाही.
- Income आणि cash-flow period-end dates जुळल्या नाहीत तर quarterly TTM reject.
- Growth साठी 8 consecutive income quarters आवश्यक; अन्यथा growth NA राहते.
- Historical Balance Sheet उपलब्ध नसेल तर ROE/ROCE NA राहतात; latest aligned BS वर Debt/Equity शक्य असल्यासच भरला जातो.
- Missing/unaligned quarterly data मुळे annual fallback उपलब्ध असल्यास तो वापरला जाऊ शकतो; अन्यथा existing unaligned snapshot path UNVERIFIED राहतो.

## नवीन audit columns
`RevenueTTMINR`, `PreviousRevenueTTMINR`, `NetProfitTTMINR`, `PreviousNetProfitTTMINR`, `EBITTTMINR`, `InterestExpenseTTMINR`, `TTMQuarterPeriods`, `TTMQuarterlyAlignmentStatus`, `TTMCalculationReason`.

ही audit columns `METRIC_COLUMNS` मध्ये जोडलेली नाहीत. त्यामुळे existing completeness count आणि fundamental shortlist thresholds बदलत नाहीत.

## बदललेल्या फाइल्स
- `fundamental_data_provider.py`
- `fundamental_filter.py`
- `test_fundamental_shortlist_and_alignment.py`

## Local validation
- Focused fundamental + delivery + liquidity + pipeline regression suites: **77 PASS**.
- Python compile: **PASS**.
- संपूर्ण repository `pytest -q` चालवण्याचा प्रयत्न 300 सेकंदांच्या timeout मध्ये पूर्ण झाला नाही; त्यामुळे संपूर्ण suite PASS असल्याचा दावा नाही.

## Deployment
हा local patch आहे; GitHub वर commit/push/deploy केलेला नाही. ZIP मधील फाइल्स review करून repository मध्ये लागू करा, मग GitHub Actions logs आणि reports तपासा. Live Yahoo provider fetch किंवा official filing verification या local test run मध्ये केलेले नाही.
