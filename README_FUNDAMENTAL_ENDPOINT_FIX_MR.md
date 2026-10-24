# NSE V8 — Fundamental Official Filing Final Fix (24-10-2026)

## मूळ चूक — history आणि reference तपासून सापडलेली

Latest GitHub Actions log (`logs_108615499818.zip`) मध्ये endpoint ला HTTP 200 मिळाले, पण `payload_items=40`, `financial_term_matches=0`, `periods_parsed=0`, `accepted=0` होते. याचा अर्थ API पूर्णपणे बंद नव्हती; parser NSE च्या actual Integrated Filing schema शी जुळत नव्हता.

NSE Integrated Filing API च्या public reference implementation `Baka7/nse-market-scripts/fetch_financial_results_range.py` मध्ये हे fields/parameters वापरलेले आहेत:

- Query parameters: `index=equities`, `from_date`, `to_date`, `period_ended=all`, `type=Integrated Filing- Financials`, `page=0`, `size=...`
- Count probe response: `totalCount`
- Actual row fields: `creation_Date` (filing timestamp), `symbol`, `qe_Date` (quarter end), `cmName`, `type_Sub`, `seq_Id`

आपल्या आधीच्या code मध्ये `broadCastDate` आणि `toDate` सारखे aliases होते, पण `creation_Date` आणि `qe_Date` नव्हते; `period_ended=all` देखील नव्हते आणि pagination `page=1` पासून सुरू होत होती. त्यामुळे NSE ने records दिले तरी parser ला योग्य publication date/period-end ओळखता येत नव्हते.

References:
- NSE official Integrated Filing - Financials page: https://www.nseindia.com/companies-listing/corporate-integrated-filing
- Working reference implementation: https://github.com/Baka7/nse-market-scripts/blob/main/fetch_financial_results_range.py

## या final patch मध्ये काय बदलले

1. `creation_Date` ला official filing/publication timestamp म्हणून parse केले.
2. `qe_Date` ला official quarter/financial period end म्हणून parse केले.
3. `cmName`, `type_Sub`, `seq_Id` आणि XBRL link fields diagnostics/record handling मध्ये समाविष्ट केले.
4. NSE च्या reference प्रमाणे `period_ended=all` आणि zero-based `page=0` वापरले.
5. आधी `size=1` वापरून `totalCount` probe; मग `totalCount + 50` records मागितले. API size cap लावल्यास deduplicated page fallback आहे.
6. `symbol + qe_Date + creation_Date` नसल्यास row `VERIFIED` होत नाही. तारीख अंदाजाने भरली जात नाही.
7. `outputs/v8_official_fetch_diagnostics.csv` मध्ये total count, response keys, sample record fields, pages, stop reason आणि accepted count नोंदवले जातात.
8. फक्त `fundamental_official_filings.py` आणि त्याची focused tests बदलली आहेत. RVOL, Delivery, Liquidity, technical, sector, news, corporate events, risk किंवा shortlist rules बदललेले नाहीत.

## Local validation

- Focused Official Filing tests: **13 PASS**
- Existing project regression suite (the same test set used by the latest workflow): **60 PASS**
- Python compile check: **PASS**
- NSE Live API verification: **अजून बाकी** — local tests mocked API responses वापरतात. Live acceptance फक्त patch GitHub वर लागू करून नवीन NSE Data Test run झाल्यावरच सिद्ध होईल.

## लागू करण्याची पद्धत

ZIP मधील दोन्ही files repository च्या root मध्ये पूर्णपणे replace करा:

1. `fundamental_official_filings.py`
2. `test_fundamental_official_filings.py`

Commit/push करून GitHub Actions मधील NSE Data Test run करा. नवीन report ZIP मधील `outputs/v8_official_fetch_diagnostics.csv` मध्ये हे तपासा:

- `ReportedTotalCount`
- `PayloadKeys`
- `SampleMatchedItemKeys` आणि `SampleMatchedItemFields`
- `PagesFetched` / `PaginationStopReason`
- `PublicationDateParsed`
- `PeriodEndParsed`
- `AcceptedRows`

`AcceptedRows > 0` असणे एकट्याने सर्व fundamental metrics verified असल्याचा पुरावा नाही. प्रत्येक candidate साठी exact symbol, period end, official filing timestamp आणि EOD cutoff match आवश्यक आहे. Live run ने योग्य rows न दिल्यास `UNVERIFIED` कायम ठेवायचे; तारीख किंवा financial period बनवून भरायचा नाही.
