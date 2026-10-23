# NSE V8 Fundamental Official Filing Verification — follow-up fix

## या patch मध्ये काय बदलले?

1. NSE announcement subject मध्ये `30th June, 2026`, `June 30, 2026`, `30-Jun-2026` आणि `quarter and year ended` अशा common formats मधून Financial Period End शोधण्याची क्षमता सुधारली.
2. Board meeting ची तारीख किंवा description मधील कोणतीही random तारीख Financial Period End म्हणून स्वीकारली जात नाही.
3. Announcement date parser ISO, NSE day-first strings आणि epoch seconds/milliseconds हाताळतो.
4. Live NSE fetch fail झाला किंवा parseable rows शून्य आल्या, तर आधीचा official filing cache fallback म्हणून वापरला जातो.
5. Cache मधील records वापरताना FinancialPeriodEnd आणि PublicationDate दोन्ही EOD cutoff च्या आत असणे आवश्यक आहे. EOD नंतरची माहिती जुन्या analysis साठी verify केली जात नाही.
6. Official filing न सापडल्यास `UNVERIFIED` कायम राहते; तारीख बनवून भरली जात नाही.
7. Delivery A/B, ₹2 crore Liquidity, RVOL आणि इतर modules मध्ये बदल केलेला नाही.

## बदललेल्या फाइल्स

- `fundamental_official_filings.py` — पूर्ण replacement.
- `test_fundamental_official_filings.py` — नवीन regression tests समाविष्ट केलेली पूर्ण replacement.

## Local test results

- Fundamental, Delivery, Liquidity, Mainboard, Risk आणि Pipeline targeted suite: **51 PASS**.
- Python compile check (`fundamental_official_filings.py`, `fundamental_data_provider.py`, `fundamental_filter.py`, `delivery_filter.py`, `liquidity_filter.py`, `volume_gainer.py`): **PASS**.
- Live NSE endpoint test: या run मध्ये केलेली नाही.
- Yahoo/NSE official financial-statement metrics parsing: या patch चा भाग नाही. त्यामुळे metrics period alignment `VERIFIED` होईपर्यंत Fundamental Rank तयार न होणे हा अपेक्षित सुरक्षित वर्तन आहे.

## GitHub वर कसे लागू करायचे?

1. ZIP Extract करा.
2. त्यातील `AI-Trading-Bot-main/fundamental_official_filings.py` आणि `AI-Trading-Bot-main/test_fundamental_official_filings.py` या दोन फाइल्स त्यांच्या त्याच repository paths वर Replace करा.
3. फक्त या दोन फाइल्स commit/push करा.
4. `NSE Data Test` workflow चालवा.
5. Report ZIP मधील `outputs/v8_official_publication_date_verification.csv` आणि `outputs/v8_official_financial_results_filings.csv` तपासा.

**टीप:** संपूर्ण repository overwrite करू नका. हा patch official publication-date extraction/cache reliability सुधारतो; तो सर्व financial metrics स्वतःहून पूर्ण करत नाही.
