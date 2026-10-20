NSE V8 ROOT-CAUSE FIX — 20-Oct-2026

नवीनतम logs_106817728483.zip मध्ये मूळ दोष स्पष्ट दिसतो:
- 19-Oct-2026 साठी sector archive cache मध्ये फक्त 146 rows होत्या.
- Exact configured-name matching मध्ये 23 पैकी 17 सेक्टरच जुळले.
- तरी sector_data.py मधील _download_daily_index_file() ने कोणतीही non-empty cache file पूर्ण समजून थेट CACHE_HIT करून परत केली.
- त्यामुळे अधिकृत archive host वरून refresh करण्याची संधीच मिळत नव्हती.
- परिणाम: sector_history.csv मध्ये 19-Oct-2026 साठी 17 rows; सहा सेक्टर 16-Oct वरच थांबले.

या Patch मध्ये:
1. Cached all-indices CSV मधील Index Name वरून 23 configured sector names चे exact coverage मोजले जाते.
2. Coverage अपूर्ण असल्यास CACHE_INCOMPLETE नोंदवून दोन्ही अधिकृत NSE archive hosts पुन्हा तपासले जातात.
3. जास्त complete fresh CSV मिळाल्यास cache update होतो.
4. Refresh अयशस्वी झाल्यास जुनी cache file delete/overwrite होत नाही; सुरक्षित fallback म्हणून वापरली जाते.
5. अंदाजे close values किंवा दुसऱ्या index चे values भरले जात नाहीत.

फाइल्स:
- sector_data.py (पूर्ण replacement)
- test_sector_archive_cache_revalidation.py (नवीन regression tests)

मुख्य AI-Trading-Bot repository मध्येच वापरा. Delivery Watchlist वेगळ्या प्रोजेक्टला हात लावू नका.
Delivery Filter, Liquidity Filter, volume_gainer.py किंवा News logic या patch मध्ये बदललेले नाहीत.

Live सत्यापन:
GitHub Actions च्या पुढील NSE Data Test मध्ये CACHE_INCOMPLETE, FETCH/CACHE_REFRESHED आणि exact_date_sectors=23/23 तपासा.
जर official hosts सुद्धा incomplete CSV परत देत असतील, तर 23/23 मिळाले असे म्हणू नका; WAIT_FOR_DATA कायम राहील.
