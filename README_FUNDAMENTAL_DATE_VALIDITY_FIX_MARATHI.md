# NSE V8 — Fundamental Date Validity Fix (2026-10-23)

## काय दुरुस्त केले?
- Yahoo Finance डेटा डाउनलोड केल्याची तारीख आता `AsOfDate` म्हणून नोंदवली जात नाही. ती `DataRetrievedAtUTC` मध्ये वेगळी नोंदते.
- `AsOfDate` फक्त financial data publicly available झाल्याची verified date असल्यास भरावी. Provider ती date देत नसेल तर रिकामी ठेवली जाते आणि `PUBLICATION_DATE_UNVERIFIED` नोंदते.
- `nextFiscalYearEnd` ला financial period end म्हणून चुकीने वापरणे बंद केले. त्याऐवजी `mostRecentQuarter` किंवा `lastFiscalYearEnd` वापरले जातात; उपलब्ध नसल्यास period end unknown राहतो.
- `FinancialPeriodEnd` EOD तारीखीनंतर असेल तर `FINANCIAL_PERIOD_END_AFTER_EOD` audit reason मिळतो.
- Fundamental collection अजूनही Delivery A/B मधील stocks reject करत नाही. Missing/unverified data स्पष्टपणे दाखवले जाते.

## महत्त्वाची मर्यादा
Yahoo Finance हा secondary source आहे. Period end माहिती असणे म्हणजे त्या financial statements ची publication date सिद्ध झाली असे नाही. `PUBLICATION_DATE_UNVERIFIED` असलेल्या records ना historical EOD backtest साठी verified मानू नये; official filing/publication date तपासणे आवश्यक आहे.

## तपासणी
- `test_fundamental_filter.py` आणि `test_fundamental_data_provider.py`: focused tests पास.
- हा patch GitHub Actions मध्ये deploy झालेला आहे असे समजू नये; ZIP लागू करून नवीन workflow run तपासावा.
