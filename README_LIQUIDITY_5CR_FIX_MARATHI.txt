NSE V8.0 — LIQUIDITY FILTER (₹2 CRORE CURRENT THRESHOLD)

हा दस्तऐवज आधीच्या ₹5 कोटी threshold ची दुरुस्ती स्पष्ट करतो. सध्याचा वापरकर्ता-मान्य threshold ₹2 कोटी आहे.

मुख्य नियम:
1. मागील 5 वैध सत्रांपैकी प्रत्येक दिवशी Delivery >= 60%.
2. त्यानंतर मागील 20 पूर्ण EOD सत्रांची सरासरी दैनिक उलाढाल (NSE CM Bhavcopy TtlTrfVal) किमान ₹2,00,00,000 असणे आवश्यक.
3. त्यानंतर Technical, Sector, News, Risk/Reward आणि Final EOD तपासण्या चालतात.

Liquidity निकाल:
- PASS_GE_2CR_AVG_DAILY_VALUE: 20 दिवसांची सरासरी उलाढाल >= ₹2 कोटी.
- FILTERED_OUT_LT_2CR_AVG_DAILY_VALUE: पूर्ण डेटा असून सरासरी ₹2 कोटींपेक्षा कमी.
- WAIT_FOR_DATA: 20 सत्रे किंवा आवश्यक traded-value डेटा अपूर्ण/गहाळ.

Audit: outputs/v8_liquidity_first_audit.csv

Daily Bhavcopy मधील traded value हा उलाढालीवर आधारित liquidity proxy आहे. Bid-ask spread आणि market depth उपलब्ध डेटातून तपासले जात नाहीत.
