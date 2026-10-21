NSE V8 EOD SYSTEM — PHASE 2 FUNDAMENTAL GATE

काय बदलले:
1. Delivery आणि 20-session Liquidity gates नंतर Fundamental gate जोडला.
2. Fundamental CSV आणि threshold configuration नसल्यास स्टॉक PASS होत नाही; WAIT_FOR_DATA राहतो.
3. पूर्ण आर्थिक metrics, source, source URL आणि financial AsOfDate आवश्यक आहेत.
4. Threshold fail झाल्यास REJECT; डेटा/config अपूर्ण असल्यास WAIT_FOR_DATA.
5. फक्त FundamentalStatus=PASS असलेले स्टॉक्स RVOL/technical ranking मध्ये पुढे जातात.
6. Final shortlist जास्तीत जास्त 4 stocks; कमी stocks किंवा cash allowed.
7. Portfolio risk / position sizing controls added. Account equity, risk budget,
   stop-distance cap, current total exposure and sector exposure must be verified
   in data/inputs/risk_config.json; missing values => WAIT_FOR_DATA.
8. Reports: v8_fundamental_report.csv, v8_fundamental_passed.csv,
   v8_fundamental_rejected.csv, v8_fundamental_wait_for_data.csv,
   v8_risk_control_report.csv, v8_technical_report.csv, v8_selection_status_report.csv,
   v8_passed_stocks.csv, v8_rejected_stocks.csv, v8_wait_for_data_stocks.csv,
   v8_final_shortlist.csv (maximum 4 stocks).

महत्त्वाची मर्यादा:
- Fundamental data source integration स्वयंचलित नाही. data/inputs/fundamental_metrics.csv मध्ये
  पडताळलेले डेटा आणि SourceURL द्यावा लागेल.
- data/inputs/fundamental_thresholds.json मध्ये व्यावसायिकदृष्ट्या मान्य thresholds स्पष्टपणे
  भरल्याशिवाय सर्व stocks WAIT_FOR_DATA राहतील. Thresholds मुद्दाम गृहीत धरलेले नाहीत.
- data/inputs/risk_config.json मध्ये खात्याचे भांडवल व exposure माहिती पडताळून भरल्याशिवाय
  RiskControlStatus PASS होणार नाही.
- Production workflow मध्ये deploy केलेले नाही; हा replacement patch आहे.

Tests:
python -m pytest -q test_fundamental_filter.py test_risk_controls.py test_selection_pipeline_order.py test_liquidity_filter.py test_delivery_rule.py
