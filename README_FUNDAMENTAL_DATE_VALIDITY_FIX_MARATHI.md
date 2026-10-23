# NSE V8 — Fundamental Date Validity Fix (23-Oct-2026)

## या patch मध्ये काय बदलले?

1. `DataRetrievedAtUTC` हा डेटा download/fetch केल्याचा UTC timestamp स्वतंत्र ठेवला आहे.
2. `AsOfDate` / `FinancialPeriodEnd` हे financial period साठी वापरले जातात; retrieval timestamp ला financial date समजले जात नाही.
3. `nextFiscalYearEnd` आता `FinancialPeriodEnd` म्हणून वापरला जात नाही.
4. `PublicationDate` व `PublicationDateStatus` वेगळे fields आहेत. Yahoo/yfinance कडून विश्वसनीय publication date मिळत नसल्यास ती बनवून लिहिली जात नाही; `UNVERIFIED` राहते.
5. EOD तपासणीमध्ये financial period आणि verified publication date स्वतंत्रपणे तपासले जातात.
6. Yahoo/yfinance record मध्ये FinancialPeriodEnd उपलब्ध नसेल तर जुन्या `AsOfDate` retrieval value वरून period end अंदाजला जात नाही.
7. Delivery A/B candidate rows collection टप्प्यात हटवले जात नाहीत. डेटा अपूर्ण असल्यास status/reason मध्ये दाखवले जाते.
8. Manual/user-verified metric values overwrite केले जात नाहीत.

## GitHub मध्ये कसे लागू करायचे?

1. ZIP डाउनलोड करून extract करा.
2. `AI-Trading-Bot-main` folder मधील खालील files repository मध्ये त्याच paths वर replace करा:
   - `fundamental_data_provider.py`
   - `fundamental_filter.py`
   - `test_fundamental_data_provider.py`
   - `test_fundamental_filter.py`
3. `README_FUNDAMENTAL_DATE_VALIDITY_FIX_MARATHI.md` reference म्हणून ठेवा.
4. Commit/push केल्यानंतर GitHub Actions मधील NSE Data Test workflow चालवा.
5. नवीन report ZIP तपासा आणि मला पाठवा.

## Local validation

खालील focused/regression test command चालवला:

`python -m pytest -q test_fundamental_filter.py test_fundamental_data_provider.py test_main_board_filter.py test_delivery_rule.py test_liquidity_filter.py test_risk_controls.py test_selection_pipeline_order.py test_v8_regression.py`

Result: **68 passed**

Python compile check: **PASS**

## मर्यादा / महत्त्वाची नोंद

हा patch date semantics आणि audit flags सुधारतो; तो स्वतःहून Yahoo Finance कडून official filing publication date आणत नाही आणि missing ROE/इतर metrics तयार करत नाही. Publication date `UNVERIFIED` असल्यास record `PARTIAL_DATA` राहील. अधिकृत NSE/BSE/company filing मधून publication date जोडण्यासाठी स्वतंत्र source-ingestion काम आवश्यक आहे.
