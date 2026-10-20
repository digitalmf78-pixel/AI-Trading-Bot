NSE SWING TRADING V8.0 — SECTOR MAPPING + NEWS/ANNOUNCEMENT FINAL FIX
तारीख: 20-10-2026

या पॅचचा उद्देश
----------------
Sector Mapping आणि NSE announcement/news matching मधील वारंवार येणाऱ्या अडचणी एकाच मर्यादित पॅचमध्ये दुरुस्त करणे. Delivery, Liquidity, Volume/RVOL, Top-20 किंवा Technical/Risk-Reward नियम बदललेले नाहीत.

ZIP मधील फाइल्स
---------------
1. sector_data.py                 (पूर्ण replacement)
2. news_catalyst.py               (पूर्ण replacement; daily Delivery >=60% gate कायम)
3. test_sector_news_final_fix.py  (नवीन regression tests)
4. TEST_RESULTS.txt               (स्थानिक चाचण्यांचा सारांश)

दुरुस्त केलेल्या मुख्य समस्या
----------------------------
SECTOR MAPPING:
- NSE all-indices archive मध्ये काही index names च्या शेवटी 'Index' असते, काही ठिकाणी नसते. आधी फक्त Healthcare साठी alias होता. आता trailing 'Index' suffix exact पद्धतीने normalize होतो; fuzzy/substring mapping नाही.
- Official classification मधील TEXTILES, CONSTRUCTION आणि TRANSPORT SERVICES / LOGISTICS SOLUTION PROVIDER यांना योग्य official benchmark शी जोडण्यासाठी Nifty Non-Cyclical Consumer, Nifty Construction आणि Nifty Transportation & Logistics यांचे tracked benchmarks जोडले.
- Broad 'SERVICES' label पेक्षा specific official industry (उदा. TRANSPORT SERVICES) अधिक अचूक असल्यास industry mapping ला प्राधान्य.
- अधिकृत classification मिळत नसेल तर अंदाजाने sector दिला जात नाही; WAIT_FOR_DATA कायम राहतो.
- Nifty Indices history API साठी JSON body स्पष्टपणे serialize करून पाठवला आहे, ज्यामुळे regression tests मधील request contract जुळतो.

NEWS / ANNOUNCEMENTS:
- NSE RSS/API च्या exact symbol/ticker field शी जुळणारी नोंद आता headline मध्ये ticker नसला तरी स्वीकारली जाते.
- MARICO सारख्या distinctive single-word registered company names ची matching दुरुस्त केली; TECH सारखे generic one-word names अजूनही match होत नाहीत.
- Official NSE issuer/date API प्रत्येक candidate साठी चालतो; RSS मध्ये एक announcement सापडला म्हणून बाकी issuer filings वगळल्या जात नाहीत.
- API calls मध्ये एक shared warmed session वापरला जातो.
- Official API ने यशस्वीपणे empty response दिल्यास तो त्या issuer/window साठी coverage मानला जातो; API blocked/failed असल्यास चुकीने NO_NEWS_FOUND देण्याऐवजी WAIT_FOR_DATA राहतो.
- Upstox सारख्या share-price/chart/profile pages ना catalyst news समजले जात नाही.
- RSS आणि API मधील duplicate filing rows ticker + timestamp + headline ने deduplicate होतात.

महत्त्वाचे: Delivery नियम
-----------------------
- मागील पाच वैध ट्रेडिंग सेशन्समधील प्रत्येक दिवसाची Delivery >= 60.00% आवश्यक.
- AvgDelivery5D हा फक्त display/analysis value; पात्रतेसाठी वापरला जात नाही.
- अपूर्ण पाच दिवसांचा डेटा असल्यास WAIT_FOR_DATA.

GitHub वर लागू करण्याची पद्धत
-----------------------------
मुख्य repository: digitalmf78-pixel/AI-Trading-Bot
1. ZIP Extract करा.
2. GitHub मध्ये sector_data.py उघडा आणि ZIP मधील पूर्ण sector_data.py ने Replace करा.
3. news_catalyst.py साठीही पूर्ण फाइल Replace करा.
4. test_sector_news_final_fix.py नवीन फाइल म्हणून Add करा.
5. Commit करा आणि NSE Data Test workflow चालवा.
6. Artifact मधून sector_candidate_mapping_YYYYMMDD.csv, sector_history.csv, v8_premarket_news_check.csv आणि v8_catalyst_top20.csv तपासा.

काय अपेक्षित आहे
----------------
- Sector history मधील index name suffix mismatch दूर होऊन अधिक indices exact-date history मध्ये मॅप होऊ शकतात.
- LAGNAM/SRTL सारख्या TEXTILES, BCPL सारख्या CONSTRUCTION आणि OMFREIGHT सारख्या logistics classification साठी official benchmark उपलब्ध होतो.
- Unknown/unclassified SME stocks अजूनही WAIT_FOR_DATA राहू शकतात. हा योग्य fail-closed परिणाम आहे; बनावट mapping करायची नाही.
- News coverage वाढू शकते, पण secondary news कधीही official announcement समजली जाणार नाही.

स्वतंत्र Delivery Watchlist टेस्ट प्रोजेक्टला बदल लागू करू नका.
