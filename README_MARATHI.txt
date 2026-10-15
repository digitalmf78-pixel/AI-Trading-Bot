NSE V8 NEWS DIAGNOSTIC SOLUTION

हे patch news_catalyst.py पूर्ण replacement आहे. उद्देश:
- दोन्ही अधिकृत NSE RSS feeds चा fetch status आणि item count लॉग करणे.
- किती items तारीख filter मध्ये राहिले/बाहेर गेले ते दाखवणे.
- कोणत्या headline ने कोणता issuer match केला ते दाखवणे.
- secondary news fetch/match count दाखवणे.
- अंतिम official/secondary row counts दाखवणे.
- VERIFIED/primary दर्जा वाढवून देत नाही; existing conservative issuer matching कायम ठेवतो.
- volume_gainer.py आणि delivery_filter.py बदलत नाही.

GitHub मध्ये:
1. Repository उघडा -> news_catalyst.py
2. Edit (pencil) -> संपूर्ण जुना code हटवा.
3. या ZIP मधील news_catalyst.py चा संपूर्ण code paste करा -> Commit changes.
4. Actions -> NSE Data Test -> Run workflow.
5. Logs मधील [NEWS-DIAG] शोधा.

निदान कसे वाचायचे:
- OFFICIAL_FEED_FETCH_FAIL: URL/network/HTTP समस्या.
- OFFICIAL_FEED_FETCH_OK items=0: feed रिकामा/बदललेला.
- items जास्त, date_valid=0: pubDate/cutoff समस्या.
- date_valid जास्त, issuer_matches=0: company-name/ticker matching समस्या.
- official_rows=0 आणि secondary_rows>0: official NSE feed मधून verified match नाही; secondary बातमीला official मानू नका.

Tests:
python -m py_compile news_catalyst.py
python test_news_catalyst_parser.py
python test_news_catalyst_matching.py
