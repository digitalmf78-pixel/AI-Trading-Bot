# NSE V8 — Fundamental Verification & Date-Safe Ranking Patch

## काय सुधारले

1. `DataRetrievedAtUTC` स्वतंत्र नोंदवते. डेटा download झाल्याची वेळ ही financial period किंवा result publication date समजली जात नाही.
2. Financial period शोधताना `nextFiscalYearEnd` वापरले जात नाही. Statement column dates प्राधान्याने घेतल्या जातात; provider metadata fallback असल्यास official filing verification आवश्यक राहते.
3. NSE corporate announcements मधून symbol + exact `FinancialPeriodEnd` + publication date जुळल्यावरच `PublicationDateStatus=VERIFIED` होते.
4. EOD cutoff नंतरची publication date किंवा financial period ranking साठी मान्य होत नाही.
5. `MetricPeriodAlignmentStatus` VERIFIED नसल्यास score/rank तयार होत नाही. वेगवेगळ्या periods मधील Yahoo snapshot/statement metrics एकत्र करून चुकीचा score दिला जाणार नाही.
6. Official filing fetch fail झाल्यास candidates delete होत नाहीत; date `UNVERIFIED` राहते.
7. `volume_gainer.py` आणि workflow मध्ये EOD cutoff integration आहे. यात आधीचे Delivery report fallback आणि ₹2 crore liquidity threshold कायम ठेवले आहेत.
8. Delivery A/B चे नियम बदललेले नाहीत.

## Reports

- `outputs/v8_official_financial_results_filings.csv`
- `outputs/v8_official_publication_date_verification.csv`
- `outputs/v8_fundamental_provider_diagnostics.csv`
- `outputs/v8_fundamental_report.csv`

## Tests

- Targeted Fundamental + Delivery + Liquidity + Pipeline tests: 41 PASS.
- `py_compile`: PASS.
- Full `pytest -q test_*.py`: 157 PASS, 2 FAIL. दोन्ही failures `test_top50_rvol_selection.py` मधील जुने tests आहेत जे `volume_gainer.select_top50_by_rvol` शोधतात. Current approved logic मध्ये Top-50 cap नाही; म्हणून हे tests stale आहेत आणि या patch मध्ये बदललेले नाहीत.
- Live NSE endpoint / live Yahoo data verification या local run मध्ये केलेले नाही. GitHub Actions run नंतर actual verification counts पाहणे आवश्यक आहे.

## GitHub वर लागू करणे

**संपूर्ण repository overwrite करू नका.** ZIP मधील फाइल्सच त्यांच्या त्याच relative path वर add/replace करा. `volume_gainer.py` आणि workflow फाइल पूर्णपणे replace कराव्या लागतील; या ZIP मधील आवृत्तीत Delivery fallback व ₹2 crore liquidity बदल जतन केले आहेत. Commit/Push नंतर `NSE Data Test` workflow चालवा.

**महत्त्वाचे:** Yahoo Finance metrics हे secondary data आहेत. NSE filing publication date verify झाली तरी सर्व metric values एकाच financial period शी aligned आहेत याचा स्वतंत्र पुरावा नसल्यास score/rank रोखलेला राहतो. ही मुद्दाम conservative सुरक्षा आहे; official statement metrics parsing पुढील काम आहे.
