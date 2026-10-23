# NSE V8 Fundamental Completeness Patch (Marathi)

## काय बदलले?
- Fundamental provider ला EOD तारीख दिली जाते; EOD नंतरचे statement periods गणनेतून वगळले जातात.
- `nextFiscalYearEnd` ला FinancialPeriodEnd म्हणून वापरले जात नाही.
- Provider-reported ROE नसल्यास net income आणि equity वापरून ROE काढण्याचा स्पष्ट fallback जोडला. Average equity उपलब्ध असल्यास त्याचा वापर होतो; अन्यथा ending-equity proxy म्हणून नोंद होते.
- `ROECalculationMethod` मध्ये ROE provider ने दिला की गणना करून मिळाला हे नोंदते.
- Retrieval timestamp, financial period आणि publication date स्वतंत्र ठेवले आहेत.
- Publication date verified नसेल किंवा EOD नंतरची असेल तर stock collection मध्ये राहतो, पण FundamentalScore/Rank दिले जात नाहीत.
- Delivery A/B आणि इतर technical/news/liquidity modules चे selection rules बदललेले नाहीत.

## महत्त्वाच्या मर्यादा
- Yahoo/yfinance हा secondary, best-effort source आहे. हा patch स्वतःहून NSE filing publication dates शोधत किंवा verify करत नाही.
- Publication date न पडताळलेल्या records ना `PARTIAL_DATA` ठेवणे अपेक्षित आहे; त्यांना verified score देत नाही.
- ROE fallback हा calculated proxy आहे; अधिकृत filing मधील ROE समजून वापरू नये. `ROECalculationMethod` तपासा.

## लागू करण्यासाठी
ZIP मधील फाइल्स त्याच relative paths ने GitHub repository मध्ये replace करा, commit/push करा आणि NSE Data Test workflow चालवा. Workflow report मध्ये `ROECalculationMethod`, `PublicationDateStatus`, `FundamentalScoreEligibilityStatus` तपासा.
