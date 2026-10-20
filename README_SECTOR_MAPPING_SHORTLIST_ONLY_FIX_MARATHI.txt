NSE SWING TRADING V8.0 — Sector Mapping Shortlist-Only + Cache Revalidation Fix
Date: 20 October 2026

उद्देश
- sector_map.csv मध्ये फक्त सध्याच्या shortlist/analysis-candidate stocks चे mapping साठवणे.
- अधिकृत sector-index constituent feeds हे फक्त in-memory reference म्हणून वापरणे.
- सध्याच्या shortlist मध्ये नसलेले जुने mapping rows cache मधून काढणे.
- sector_history.csv साठी अधिकृत 23 tracked indices चा इतिहास कायम ठेवणे.
- NSE all-indices archive cache मध्ये 23 पैकी काही sectors कमी असतील तर cache ला complete समजू नये; official archive पुन्हा fetch करावा.
- नवीन official CSV मध्ये 23/23 coverage असल्यासच cache replace करावा.
- official refresh अपयशी झाल्यास आधीचा cache नष्ट करू नये; उपलब्ध अपूर्ण cache fallback म्हणून परत द्यावा आणि log मध्ये coverage स्पष्ट दाखवावे.
- अज्ञात/अपूर्ण mapping साठी WAIT_FOR_DATA; sector अंदाजाने ठरवायचा नाही.

बदललेल्या फाइल्स
1. sector_data.py — पूर्ण replacement file
2. test_sector_mapping_cache_reconciliation.py — shortlist-only आणि stale-cache regression tests
3. test_nse_official_index_api.py — archive cache coverage/revalidation साठी 3 regression tests जोडले

स्थानिक पडताळणी
- py_compile sector_data.py आणि संबंधित टेस्ट फाइल्स: PASS
- test_nse_official_index_api.py: 6 tests PASS
- test_sector_mapping_cache_reconciliation.py: 5 tests PASS
- test_sector_mapping_patch.py: PASS
- test_sector_news_final_fix.py: PASS
- test_v8_regression.py: PASS
- वरील पाच test modules मिळून: 31 tests PASS

महत्त्वाचे
- हा ZIP GitHub मध्ये आपोआप लागू झालेला नाही.
- GitHub Actions मध्ये लागू करून नवीन run artifact/log तपासेपर्यंत production verification पूर्ण समजू नका.
- Delivery >=60% प्रत्येक 5 वैध सत्रांसाठी, Liquidity >=₹5 कोटी 20-session average, Main Board-only rule, News, Technical, 3+1 आणि Risk/Reward gates बदललेले नाहीत.
- स्वतंत्र Delivery Watchlist प्रोजेक्टला हात लावू नये.
