NSE SWING TRADING V8.0 — UPDATED STOCK SELECTION LOGIC
Date: 2026-10-23 (latest collection-stage update)

नवीन Selection क्रम:
1. NSE Mainboard मधील अधिकृतपणे पडताळलेले पात्र Equity Stocks.
2. मागील 20 पूर्ण Trading Sessions च्या सरासरी Volume वर RVOL काढणे.
3. RVOL > 1.5 असलेले सर्व Stocks निवडणे. Top 20/Top 50 ची RVOL मर्यादा नाही.
4. Delivery Category A: मागील 5 वैध वेगवेगळ्या sessions ची Average Delivery >= 60%.
5. Delivery Category B: त्याच 5 sessions पैकी प्रत्येक दिवसाची Delivery >= 60%.
   दोन्ही स्वतंत्र CSV reports आहेत. Category B ही Category A ची subset असू शकते.
6. Category A/B च्या union मधील प्रत्येक Stock साठी Fundamental Data Collection. या टप्प्यावर Fundamental मुळे stock reject करायचा नाही.
7. Existing Liquidity Filter कायम: मागील 20 पूर्ण sessions मधील average traded value >= ₹5 crore/day.
8. विद्यमान technical, news, sector आणि risk checks कायम. Strong Fundamental shortlist नंतर स्वतंत्रपणे तयार करायची.

Fundamental reports:
- outputs/v8_delivery_a_fundamentals.csv
- outputs/v8_delivery_b_fundamentals.csv
- outputs/v8_delivery_ab_combined_fundamentals.csv
- outputs/v8_fundamental_report.csv
- outputs/v8_fundamental_complete_data.csv
- outputs/v8_fundamental_partial_data.csv
- outputs/v8_fundamental_missing_data.csv

महत्त्वाचे:
- 20 पूर्ण sessions नसल्यास RVOL साठी WAIT_FOR_DATA.
- 5 distinct valid Delivery sessions नसल्यास दोन्ही Delivery Categories WAIT_FOR_DATA.
- FundamentalStatus हे data completeness दाखवते: COMPLETE / PARTIAL_DATA / MISSING_DATA. ते या टप्प्यावर PASS/REJECT gate नाही.
- Fundamental data आपोआप fetch होत नाही; सध्या data/inputs/fundamental_metrics.csv मधील पडताळलेली माहिती जोडली जाते. डेटा नसेल तर MISSING_DATA नोंदवला जातो, अंदाज लावला जात नाही.
- Strong Fundamental ranking/shortlist नंतर करायची.
- Patch GitHub वर deploy झालेला नाही. GitHub Actions आणि नवीन report ने runtime तपासणे आवश्यक आहे.

Local verification: python -m pytest -q test_*.py => 138 passed. Live NSE/GitHub Actions integration network access नसल्यामुळे verify झालेले नाही.
