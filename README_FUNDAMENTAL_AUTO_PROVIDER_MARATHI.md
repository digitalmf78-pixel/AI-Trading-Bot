# NSE V8.0 — सर्व Delivery A/B Stocks साठी Fundamental Collection

## काय बदलले?
- Delivery Category A किंवा B मध्ये PASS झालेल्या प्रत्येक unique NSE Mainboard stock साठी fundamentals गोळा करण्याचा प्रयत्न होतो.
- Category A आणि Category B चे स्वतंत्र reports कायम आहेत; Combined report मध्ये एक Stock एकदाच येतो.
- `fundamental_data_provider.py` Yahoo Finance (`yfinance`) मधून उपलब्ध financial metrics आणण्याचा प्रयत्न करतो.
- आधी `data/inputs/fundamental_metrics.csv` मध्ये manually/verified भरलेली मूल्ये प्राधान्याने जपली जातात. Provider त्या non-empty values overwrite करत नाही.
- Provider कडून एखादा metric मिळाला नाही किंवा request fail झाली तर stock reject होत नाही. Missing fields रिकामे राहतात आणि कारण `outputs/v8_fundamental_provider_diagnostics.csv` मध्ये नोंदते.
- Source URL, retrieval date आणि मिळाल्यास financial period end नोंदवले जातात.
- Strong Fundamental shortlist या टप्प्यावर बनत नाही; नंतर स्वतंत्र ranking करायची आहे.

## महत्त्वाची Data Quality सूचना
Yahoo Finance हा secondary provider आहे; तो NSE/BSE/company filing चा पर्याय नाही. Trading decision घेण्यापूर्वी शक्य असल्यास प्रत्येक metric अधिकृत company results/annual report मधून verify करा. Provider rate limit, missing fields किंवा unavailable symbol मुळे `MISSING_DATA`/`PROVIDER_ERROR` राहू शकतो. कोणतेही मूल्य अंदाजाने भरले जात नाही.

## GitHub Actions
- Workflow dependency मध्ये `yfinance` जोडले आहे.
- Compile आणि regression test मध्ये `fundamental_data_provider.py` जोडले आहे.
- `test_fundamental_data_provider.py` mocked data वापरून provider mapping, manual-value preservation आणि disabled-mode candidate retention तपासते.
- Run नंतर `outputs/v8_fundamental_provider_diagnostics.csv`, `outputs/v8_fundamental_report.csv`, `outputs/v8_delivery_a_fundamentals.csv`, `outputs/v8_delivery_b_fundamentals.csv` आणि `outputs/v8_delivery_ab_combined_fundamentals.csv` तपासा.

## Test Status (local)
- Python compile checks: PASS
- Focused pytest suite: 63 PASS
- Relevant unittest modules: 39 PASS
- Parser/corporate event tests: 9 PASS
- V8 regression script: 27/27 PASS
- Full `pytest -q` collection is not a valid suite in this repository because `delivery_60_valuation_watchlist_inline_test.py` executes script side effects/SystemExit during import. Live Yahoo/NSE access was not verified in this environment.
