# NSE V8 — Fundamental Official Filing Parser Fix (मराठी)

## या पॅचमध्ये काय दुरुस्त केले आहे?

नवीन GitHub Actions लॉगमध्ये `fundamental_official_filings.py` कडून पाच टेस्ट फेल झाल्या. त्यात दिसलेले मुख्य mismatch:

- API parameters मध्ये `period_ended=all` नव्हता.
- page index `1` पासून सुरू होत होता; regression tests zero-based `page=0` अपेक्षित करतात.
- parser ने NSE Integrated Filing-Financials मधील `creation_Date` (publication/broadcast date) आणि `qe_Date` (financial period end) ला प्रथम श्रेणीचे fields म्हणून हाताळले नव्हते.
- `totalCount`-आधारित probe आणि pagination fallback अपेक्षित पद्धतीने नव्हते.
- API ने `totalCount=0` दिल्यास स्पष्ट diagnostic अपेक्षित आहे.

## ZIP मधील फाइल्स

1. `fundamental_official_filings.py` — संपूर्ण replacement file.
2. `test_fundamental_official_filings.py` — focused regression tests.
3. `README_FUNDAMENTAL_OFFICIAL_FILING_FIX_MR.md` — या सूचना.

## लागू करण्याची पद्धत

1. GitHub repository `digitalmf78-pixel/AI-Trading-Bot` उघडा.
2. root मध्ये `fundamental_official_filings.py` उघडा.
3. संपूर्ण जुना मजकूर replace करून ZIP मधील पूर्ण नवीन फाइल paste करा आणि commit करा.
4. `test_fundamental_official_filings.py` फाइलमध्ये नवीन regression tests आधीच आहेत का तपासा. असल्यास duplicate करून ठेवू नका; नसल्यास ZIP मधील फाइल पूर्ण replace करा.
5. `NSE Data Test` workflow पुन्हा चालवा आणि नवीन logs/report तपासा.

## Local test evidence

या replacement वर:

- `python -m pytest -q test_fundamental_official_filings.py` → **13 passed**
- `python -m pytest -q test_delivery_rule.py test_delivery_filter_fallback.py test_liquidity_filter.py test_fundamental_filter.py test_fundamental_data_provider.py test_fundamental_shortlist_and_alignment.py test_fundamental_official_filings.py test_risk_controls.py test_selection_pipeline_order.py` → **60 passed**

हे local/mocked tests आहेत. **NSE Live API वरील यश अजून सिद्ध झालेले नाही.** GitHub Actions मध्ये `FinancialTermMatches`, `PeriodEndParsed`, `AcceptedRows`, `PaginationStopReason` आणि `ReportedTotalCount` तपासल्याशिवाय हा टप्पा पूर्ण समजू नये.

## Safety

- Publication date = `creation_Date` (किंवा उपलब्ध supported date field) आणि period end = `qe_Date` (किंवा explicit period field).
- Symbol, publication date आणि period end नसल्यास row `VERIFIED` म्हणून बनवू नये.
- `totalCount=0` असल्यास accepted records शून्यच राहतात.
- या पॅचमध्ये Delivery, RVOL, Liquidity, Technical, Sector, News किंवा Risk नियम बदललेले नाहीत.
