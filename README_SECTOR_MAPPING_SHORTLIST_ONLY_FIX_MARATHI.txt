NSE SWING TRADING V8.0 — Sector Mapping Shortlist-Only Patch
Date: 20 October 2026

उद्देश
- sector_map.csv मध्ये फक्त सध्याच्या shortlist/analysis-candidate stocks चे mapping साठवणे.
- अधिकृत 23 sector-index constituent feeds हे फक्त in-memory reference म्हणून वापरणे, म्हणजे shortlist मधील symbol एखाद्या tracked sector index चा constituent आहे का ते तपासता येईल.
- सर्व constituent stocks चे mapping sector_map.csv मध्ये कायमचे साठवणे थांबवणे.
- सध्याच्या shortlist मध्ये नसलेले जुने mapping rows cache मधून काढणे.
- sector_history.csv मधील अधिकृत 23 sector indices चा इतिहास बदलत नाही.
- अज्ञात/अपूर्ण mapping साठी WAIT_FOR_DATA; sector अंदाजाने ठरवायचा नाही.

बदललेले/नवीन फाइल्स
1. sector_data.py — पूर्ण replacement file
2. test_sector_mapping_cache_reconciliation.py — दोन regression tests जोडले

स्थानिक चाचण्या
- py_compile sector_data.py: PASS
- test_sector_mapping_cache_reconciliation.py: PASS (5 tests)
- test_sector_mapping_patch.py: PASS (7 tests)
- test_sector_news_final_fix.py: PASS (13 tests)
- test_nse_official_index_api.py: PASS (3 tests)
- test_v8_regression.py: PASS (27 tests)

महत्त्वाचे
- हा patch ZIP मध्ये आहे; GitHub मध्ये आपोआप लागू झालेला नाही.
- GitHub Actions मध्ये लागू करून नवीन run artifact तपासेपर्यंत production verification पूर्ण मानू नका.
- Delivery >=60% each of 5 sessions, liquidity >=₹5 crore 20-session average, Main Board-only rule, News, Technical, 3+1 आणि Risk/Reward gates बदललेले नाहीत.
- स्वतंत्र Delivery Watchlist प्रोजेक्टला हात लावू नये.
