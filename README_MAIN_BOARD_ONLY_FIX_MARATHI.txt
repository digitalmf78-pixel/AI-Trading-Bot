NSE SWING TRADING V8.0 — MAIN BOARD ONLY PATCH

या patch मध्ये फक्त मुख्य NSE V8 प्रोजेक्टच्या stock universe वर official Main Board eligibility gate जोडला आहे.

नियम:
1. NSE च्या official Equity-segment CSV मधील symbol Main Board allowlist मध्ये असणे आवश्यक.
2. NSE च्या official SME CSV मध्ये असलेला कोणताही symbol वगळला जाईल — Main Board CSV मध्ये चुकून दिसला तरी SME denylist ला प्राधान्य.
3. अधिकृत यादीत नसलेला symbol `EXCLUDED_UNVERIFIED_CLASSIFICATION` म्हणून वगळला जाईल. नाव/किंमत/series वरून अंदाज लावला जात नाही.
4. Live official CSV मिळाली नाही तर आधीची validated cache वापरली जाईल. Live आणि cache दोन्ही अनुपलब्ध/अवैध असतील तर fail-closed: त्या run मध्ये candidates पुढे जाणार नाहीत.
5. Audit: `outputs/v8_main_board_universe_audit.csv`.
6. Delivery Watchlist workflow/file बदललेले नाहीत.
7. Delivery >=60% प्रत्येक 5 valid distinct sessions, liquidity >= ₹5 crore average traded value for 20 sessions आणि बाकीचे strategy gates unchanged.

बदललेली/नवीन फाइल्स:
- `volume_gainer.py` (पूर्ण replacement)
- `main_board_filter.py` (नवीन)
- `test_main_board_filter.py` (नवीन)

Tests:
`python -m pytest -q test_main_board_filter.py`
`python -m pytest -q`
