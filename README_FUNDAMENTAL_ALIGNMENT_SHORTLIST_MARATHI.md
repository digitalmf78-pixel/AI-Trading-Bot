# NSE V8 — Period-aligned Fundamentals + Strong Fundamental Shortlist

## काय बदलले
1. `fundamental_data_provider.py`: metrics आता Yahoo `.info` snapshot वरून नाही, तर एकाच fiscal year च्या
   income statement + balance sheet + cash flow वरून काढले जातात. तिन्ही statements ची latest period-end
   तारीख सारखी असेल तरच `MetricPeriodAlignmentStatus=VERIFIED`. नाहीतर जुना path आणि `UNVERIFIED`.
2. Provider ने भरलेले (manual नसलेले) records 30 दिवसांनी पुन्हा fetch होतात (`V8_FUNDAMENTAL_REFRESH_DAYS`).
   Manual CSV values कधीच overwrite होत नाहीत.
3. `ProviderSector` column जोडला. Bank/NBFC/Insurance (`Financial Services`) साठी D/E, ROCE, Interest Coverage
   अर्थहीन असल्याने ते `WAIT_FOR_DATA` राहतात.
4. नवीन `fundamental_shortlist.py`: absolute thresholds वर PASS / FAIL / WAIT_FOR_DATA. Rows delete होत नाहीत.
   Reports: `outputs/v8_fundamental_shortlist_all.csv`, `outputs/v8_fundamental_shortlist_pass.csv`.
5. Thresholds बदलायचे असतील तर `data/inputs/fundamental_thresholds.json` मध्ये value भरा (null = default).

## Default thresholds (सुरुवातीचे; तुमच्या style नुसार बदला)
Revenue growth >= 0, Profit growth >= 0, ROE >= 10, ROCE >= 12, D/E <= 1, Interest coverage >= 3,
Operating cash flow > 0, FCF अट बंद, data age <= 548 दिवस.

## मर्यादा (प्रामाणिक नोंद)
- Annual statements वापरल्यामुळे data नवीनतम quarter चा नसतो; 18 महिने जुना होऊ शकतो.
- मागील वर्षी तोटा असल्यास growth % रिकामी (NA) राहते, म्हणून तो stock WAIT_FOR_DATA.
- Yahoo हा secondary source; भारतीय small caps साठी अनेक fields रिकामे राहू शकतात.
- Publication date NSE filing शी जुळली नाही तर shortlist मध्ये PASS येणार नाही (हेतुपुरस्सर).
- Live Yahoo/NSE आणि GitHub Actions वर verify केलेले नाही; फक्त mocked local tests.

## लागू करणे
ZIP मधील फाइल्स त्याच paths वर replace/add करा (पूर्ण repo overwrite करू नका), commit/push, मग `NSE Data Test` चालवा.
Report मध्ये `v8_fundamental_provider_diagnostics.csv` चा `AlignmentNote` column तपासा.
