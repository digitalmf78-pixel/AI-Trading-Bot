NSE V8.0 — अधिकृत NSE Historical Index Fallback दुरुस्ती
दिनांक: 20-10-2026

मूळ कारण (तुमच्या 20-Oct-2026 GitHub Actions लॉगवरून)
- Daily NSE all-indices archive मधून 23 पैकी 17 tracked indices मिळाले.
- उरलेल्या indices साठी जुना fallback https://www.niftyindices.com/Backpage.aspx/getHistoricaldatatabletoString वापरला जात होता.
- GitHub Actions लॉगमध्ये त्या endpoint वरून 302 → Sitefinity/Login redirect आणि शेवटी HTML मिळत होते; JSON नव्हता.
- त्यामुळे retry करूनही fallback rows=0 होत होते. हे index names च्या typo मुळेच आहे असे सिद्ध होत नाही; endpoint access/redirect हा स्पष्ट पुरावा आहे.

या पॅचमध्ये काय बदलले
- sector_data.py मध्ये अधिकृत NSE endpoint https://www.nseindia.com/api/historicalOR/indicesHistory साठी fallback जोडला.
- NSE homepage वरून session/cookies bootstrap करून `indexType`, `from`, `to` parameters पाठवले जातात.
- `data.indexCloseOnlineRecords` (आणि उपलब्ध direct-list form) मधील नोंदी parse केल्या जातात.
- Index name, date range आणि positive closing value तपासली जाते. दुसऱ्या index ची row, चुकीची तारीख किंवा invalid close स्वीकारली जात नाही.
- NSE API कडूनही वैध डेटा मिळाला नाही तर log मध्ये HTTP status / content type / response schema / empty records यांचे कारण दिसेल. कोणताही close अंदाजाने तयार केला जात नाही.
- जुना NiftyIndices Backpage fallback हा refresh path मधून काढला आहे, कारण लॉगमध्ये तो login-gated होता आणि प्रत्येक missing index साठी पुन्हा तेच retry करत होता.

स्थानिक चाचण्या
- Python compilation: PASS
- unittest: 39 tests PASS
- pytest (news parser + V8 regression): 31 tests PASS
- नवीन tests: nested indexCloseOnlineRecords parsing, index-name mismatch rejection, invalid close/date rejection, empty response handling.

लागू करण्याची पद्धत
1. मुख्य repo digitalmf78-pixel/AI-Trading-Bot उघडा.
2. sector_data.py संपूर्ण replace करा.
3. test_nse_official_index_api.py संपूर्ण replace करा.
4. हा README जोडून commit करा.
5. GitHub Actions मधून NSE Data Test मॅन्युअली चालवा.
6. लॉगमध्ये `[SECTOR][NSE_HISTORY_API]` आणि `fallback rows=... exact_date_sectors=...` पहा.

मर्यादा
या चाचण्या local mocks/tests आहेत. GitHub Actions मधील live NSE endpoint access अजून verify झालेला नाही; नवीन लॉग आल्यानंतरच प्रत्यक्ष coverage निश्चित करता येईल.

अस्पर्शित नियम
- मागील 5 वैध distinct sessions मधील प्रत्येक दिवसाची Delivery >= 60.00%.
- 20-session Average Daily Traded Value >= ₹5 crore.
- Volume, RVOL, Top 20 आणि बाकीचे V8 business rules बदललेले नाहीत.
- news_catalyst.py बदललेले नाही; पुढील टप्प्यात News/Announcement काम वेगळे करायचे.
- स्वतंत्र Delivery Watchlist प्रोजेक्ट समाविष्ट नाही.
