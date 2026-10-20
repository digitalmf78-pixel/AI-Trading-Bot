NSE V8.0 — DELIVERY-FIRST DAILY 60% FIX
दिनांक: 20-10-2026

या पॅचमध्ये मुख्य AI-Trading-Bot V8 प्रोजेक्टसाठी stock selection चा क्रम आणि Delivery नियम दुरुस्त केले आहेत.

नवीन क्रम:
1) Current EOD universe वर आधी Delivery Filter.
2) मागील 5 वैध, वेगळ्या trading sessions मधील प्रत्येक दिवसाची Delivery % तपासली जाते.
3) प्रत्येक दिवस >= 60.00% असेल तरच स्टॉक पुढे जातो. एक दिवस जरी 60% पेक्षा कमी असेल तर REJECT.
4) पाच sessions चा डेटा अपूर्ण असेल तर WAIT_FOR_DATA.
5) त्यानंतर आधीचे 5-day/20-day volume history checks आणि RVOL calculation चालतात.
6) त्यानंतर RVOL नुसार Top 20 निवडले जातात.
7) Top 20 नंतरचे Technical, Sector, News, Mandatory 3+1, Risk/Reward आणि Final EOD नियम बदललेले नाहीत.

AvgDelivery5D ही फक्त रिपोर्टिंग/वर्णनासाठी ठेवली आहे; ती stock qualify करण्यासाठी वापरली जात नाही.

GitHub मध्ये Replace करायच्या फाइल्स (repo root मध्ये):
- delivery_filter.py
- volume_gainer.py
- news_catalyst.py
- v8_layers_14_41.py
- test_v8_regression.py

सूचना:
- हा पॅच फक्त मुख्य digitalmf78-pixel/AI-Trading-Bot प्रोजेक्टसाठी आहे.
- स्वतंत्र Delivery Watchlist test project ला बदलू नका.
- फाइल्स replace करून Commit करा, नंतर nse-test workflow चालवा आणि नवीन artifact/log तपासा.
- हा पॅच GitHub वर आपोआप लागू केलेला नाही.

स्थानिक पडताळणी:
- Python syntax compilation: PASS
- python test_v8_regression.py: 27/27 PASS
- GitHub Actions runtime validation: अद्याप बाकी (Commit/Workflow run नंतरच).
