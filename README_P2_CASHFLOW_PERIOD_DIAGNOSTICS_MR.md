# NSE V8 P2 — Cash Flow Period Diagnostics Patch

## उद्देश
P2 Quarterly TTM calculation मध्ये 94 symbols साठी `QUARTERLY_CASHFLOW_PERIODS_NOT_ALIGNED` दिसत आहे. Raw provider statement periods उपलब्ध नसल्यामुळे mismatch चे मूळ कारण ठरवता येत नव्हते.

हा patch फक्त diagnostic visibility वाढवतो. TTM गणना, fallback, thresholds, cache refresh, Delivery/RVOL/Liquidity किंवा Master Spec बदलत नाही.

## नवीन diagnostics (`outputs/v8_fundamental_provider_diagnostics.csv`)
- `IncomeQuarterPeriodsAvailable`
- `CashFlowQuarterPeriodsAvailable`
- `BalanceSheetQuarterPeriodsAvailable`
- `CashFlowRowLabels`
- `CashFlowAlignmentMatchedPeriods`
- `CashFlowAlignmentMissingPeriods`
- `IncomeQuarterPeriodCount`
- `CashFlowQuarterPeriodCount`
- `BalanceSheetQuarterPeriodCount`

यामुळे पुढील GitHub Actions Run नंतर खालीलपैकी कोणती परिस्थिती आहे हे वेगळे करता येईल:
1. Cash Flow statement पूर्णपणे missing आहे.
2. Cash Flow मध्ये वेगळे period-end dates आहेत.
3. आवश्यक latest four periods पैकी काहीच उपलब्ध आहेत.
4. Provider row labels अपेक्षित OCF/CapEx rows पेक्षा वेगळे आहेत.
5. Income, Cash Flow आणि Balance Sheet यांचे period coverage वेगवेगळे आहे.

## महत्त्वाची सुरक्षा
- Date जबरदस्तीने align केले जात नाहीत.
- YTD values असल्याचा अंदाज लावून त्यांची बेरीज/वजाबाकी केली जात नाही.
- Quarterly TTM अपूर्ण असल्यास सध्याचा Annual Fallback / WAIT_FOR_DATA व्यवहार कायम.
- Official filing verification स्वतंत्रच राहते.

## Apply
1. `fundamental_data_provider.py` replace करा.
2. `test_fundamental_shortlist_and_alignment.py` replace करा.
3. Commit आणि push करून GitHub Actions चालवा.
4. नवीन `outputs/v8_fundamental_provider_diagnostics.csv` आणि `data/inputs/fundamental_metrics.csv` तपासा.

## Local validation
Targeted/regression suites: **79 passed**.
Python compile: **PASS**.
Live Yahoo Finance request किंवा GitHub deployment या local validation मध्ये केलेले नाही.
