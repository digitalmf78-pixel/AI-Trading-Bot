# NSE V8 P2 — One-time Re-diagnostic Cache Fix

## समस्या
Latest workflow run (checkout commit `2690baef9c8da43b5d25a45dc9b84be225073739`) मध्ये 108 Delivery A/B symbols पैकी अनेक जुन्या cache rows `EXISTING_RECORD_COMPLETE` म्हणून skip झाले. त्यांच्याकडे `TTMCalculationAttemptedAtUTC` होता; पण raw quarterly date evidence फक्त त्या वेळच्या diagnostics report मध्ये होते आणि persistent fundamental cache मध्ये नव्हते. त्यामुळे पुढील run मध्ये Income/Cash Flow quarter dates पुन्हा उपलब्ध होत नव्हते.

## या Patch मधील बदल
1. Income, Cash Flow आणि Balance Sheet quarter dates, row labels, matched/missing periods आणि counts हे `fundamental_metrics.csv` मध्ये persistent TTM audit fields म्हणून जतन होतात.
2. `TTMDiagnosticsCapturedAtUTC` हा durable marker जोडला आहे.
3. जुन्या provider-owned record मध्ये TTM attempt timestamp असूनही हा marker नसल्यास एकदाच controlled re-diagnostic fetch होईल.
4. Diagnostics marker भरल्यानंतर पुढील run मध्ये पुन्हा provider fetch होत नाही; cache मधील dates diagnostics CSV मध्ये पुन्हा दाखवले जातात.
5. Quarterly TTM calculation, Annual Fallback, 30-day refresh आणि Fundamental thresholds बदललेले नाहीत.
6. Manual/mixed metric values overwrite होत नाहीत. Quarterly TTM पूर्णपणे VERIFIED नसल्यास existing provider metrics बदलले जात नाहीत.
7. P1 cache basis आणि dated history behavior कायम ठेवले आहे.

## Replace करायच्या फाइल्स
- `fundamental_data_provider.py`
- `test_fundamental_shortlist_and_alignment.py`

## Local Validation
- Fundamental Provider / Alignment / Cache / Official Filing / Delivery / Liquidity / Pipeline related tests: **78 PASS**
- Python compile: **PASS**
- No live provider request was made during local tests.

## मर्यादा
हा patch local-tested आहे; GitHub वर commit/push केलेला नाही. पुढील GitHub Actions run मध्ये controlled re-diagnostic fetch, persisted quarter dates आणि second-run no-refetch behavior verify करणे आवश्यक आहे.
