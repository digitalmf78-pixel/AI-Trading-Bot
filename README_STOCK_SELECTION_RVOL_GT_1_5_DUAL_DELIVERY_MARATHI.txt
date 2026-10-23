NSE SWING TRADING V8.0 — UPDATED STOCK SELECTION LOGIC
Date: 2026-10-23

नवीन Selection क्रम:
1. NSE Mainboard मधील अधिकृतपणे पडताळलेले पात्र Equity Stocks.
2. मागील 20 पूर्ण Trading Sessions च्या सरासरी Volume वर RVOL काढणे.
3. RVOL > 1.5 असलेले सर्व Stocks निवडणे. Top 20/Top 50 ची RVOL मर्यादा नाही.
4. Delivery Category A: मागील 5 वैध वेगवेगळ्या sessions ची Average Delivery >= 60%.
5. Delivery Category B: त्याच 5 sessions पैकी प्रत्येक दिवसाची Delivery >= 60%.
   दोन्ही स्वतंत्र CSV reports आहेत. Category B ही Category A ची subset असू शकते.
6. आधीचे Liquidity Filter कायम: मागील 20 पूर्ण sessions मधील average traded value >= ₹5 crore/day.
7. विद्यमान Fundamental eligibility checks कायम. PASS rows साठी FundamentalScore व FundamentalRank:
   सहा metrics चे equal-weight percentile mean: Revenue Growth, Profit Growth, ROE, ROCE,
   inverse Debt/Equity, Interest Coverage. Fundamental Score नंतर RVOL tie-breaker.
8. विद्यमान technical, news, sector, risk आणि final shortlist layers कायम.

महत्त्वाचे:
- 20 पूर्ण sessions नसल्यास RVOL साठी WAIT_FOR_DATA.
- 5 distinct valid Delivery sessions नसल्यास दोन्ही Delivery Categories WAIT_FOR_DATA.
- Category A आणि B reports स्वतंत्रपणे जतन होतात.
- Fundamental metrics/thresholds न दिल्यास Fundamental filter स्वतःहून PASS देत नाही.
- हा patch GitHub वर deploy केलेला नाही. User ने GitHub Actions चालवून नवीन report तपासणे आवश्यक आहे.

Replacement files:
- volume_gainer.py
- delivery_filter.py
- fundamental_filter.py
- news_catalyst.py
- test_selection_pipeline_order.py
- test_delivery_rule.py
- test_liquidity_filter.py
- test_fundamental_filter.py
- test_v8_regression.py

Local verification:
- Python compile checks: PASS
- Test files (test_*.py): 137 PASS
- Live NSE/GitHub Actions integration: not verified in this environment (network access unavailable).
