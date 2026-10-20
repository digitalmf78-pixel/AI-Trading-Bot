NSE V8.0 — LIQUIDITY FILTER (₹5 CRORE)

मुख्य बदल:
1. विद्यमान Delivery-first नियम जसाच्या तसा: मागील 5 वैध सत्रांपैकी प्रत्येक दिवशी Delivery >= 60.00%.
2. त्यानंतर Liquidity Filter: मागील 20 पूर्ण EOD सत्रांची सरासरी दैनिक उलाढाल (NSE CM Bhavcopy TtlTrfVal) किमान ₹5,00,00,000 असणे आवश्यक.
3. त्यानंतर विद्यमान 5-day Volume History, 20-day Average Volume आणि RVOL Top 20.
4. त्यानंतर Technical, Sector, News, Mandatory 3+1, Risk/Reward आणि Final EOD नियम बदललेले नाहीत.

Liquidity निकाल:
- PASS_GE_5CR_AVG_DAILY_VALUE: 20 दिवसांची सरासरी उलाढाल >= ₹5 कोटी.
- FILTERED_OUT_LT_5CR_AVG_DAILY_VALUE: पूर्ण डेटा असून सरासरी ₹5 कोटींपेक्षा कमी.
- WAIT_FOR_DATA: 20 सत्रे किंवा आवश्यक traded-value डेटा अपूर्ण/गहाळ.

Audit: outputs/v8_liquidity_first_audit.csv

मर्यादा: Daily Bhavcopy मधील traded value हा Liquidity चा turnover-proxy आहे. Bid-ask spread आणि market depth या डेटामध्ये नाहीत; त्यांची तपासणी या पॅचमध्ये PASS म्हणून दाखवली जात नाही.

GitHub वापर:
- मुख्य digitalmf78-pixel/AI-Trading-Bot रिपॉझिटरीमध्येच फाइल्स replace/add करा.
- delivery_filter.py, news_catalyst.py, v8_layers_14_41.py आणि test_v8_regression.py हे या पॅचमध्ये संदर्भासाठी आहेत; बदल मुख्यतः volume_gainer.py मध्ये Liquidity stage जोडतो आणि liquidity_filter.py / test_liquidity_filter.py नवीन आहेत.
- ZIP मधील volume_gainer.py version हा Delivery-first daily-60% patch वर आधारित आहे. Separate Delivery Watchlist/test project मध्ये काहीही replace करू नका.
- Commit केल्यानंतर GitHub Actions চালवा અને logs/artifacts പരിശോധा. GitHub run-ന് മുമ്പ് deployed എന്നു കരുതരുത്.
