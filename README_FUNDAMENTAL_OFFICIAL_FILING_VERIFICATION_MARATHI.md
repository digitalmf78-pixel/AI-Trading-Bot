# NSE V8 — Fundamental Official Filing Verification (मराठी)

## काय केले आहे
- Fundamental provider आता NSE corporate-announcements endpoint मधून financial-results announcements आणण्याचा प्रयत्न करतो.
- फक्त description मध्ये financial-results संदर्भ आणि स्पष्ट period-end date असलेली नोंदच वापरली जाते.
- `TckrSymb` आणि `FinancialPeriodEnd` दोन्ही exact match झाल्याशिवाय publication date `VERIFIED` होत नाही.
- EOD नंतरची publication date ऐतिहासिक ranking साठी स्वीकारली जात नाही.
- NSE endpoint बंद/blocked असल्यास provider चे बाकीचे collection थांबत नाही; publication dates `UNVERIFIED` राहतात.
- candidate rows किंवा Delivery A/B logic बदललेले नाहीत.

## नवीन outputs
- `outputs/v8_official_financial_results_filings.csv` — NSE announcements मधील exact period-matched financial-result records.
- `outputs/v8_official_publication_date_verification.csv` — verified/unverified/fetch-failed कारणांसह audit.
- `data/inputs/fundamental_metrics.csv` — matched official publication date/status, जेव्हा पुरेसा पुरावा उपलब्ध असेल.

## महत्त्वाची मर्यादा
NSE announcement description मध्ये period-end स्पष्ट नसेल किंवा NSE API access blocked असेल तर publication date जबरदस्तीने भरली जात नाही. अशा records `UNVERIFIED` राहतात. ही module NSE API वर live successful access हमखास देत नाही; GitHub Actions report मध्ये `FETCH_FAILED`/`UNVERIFIED` कारण तपासा. BSE filings साठी या patch मध्ये स्वतंत्र fetcher जोडलेला नाही.

## लागू करणे
ZIP मधील फाइल्स त्यांच्या relative path नुसार GitHub repository मध्ये replace/add करा, commit/push करा आणि `NSE Data Test` workflow चालवा. Workflow artifacts मध्ये `v8_official_publication_date_verification.csv` तपासा.
