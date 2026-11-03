# NSE V8 — XBRL FX Reconciliation आणि Q4 CFO Audit Fix

## काय दुरुस्त केले

1. जुन्या cash-flow cross-foot मध्ये CFO + CFI + CFF ची बेरीज थेट post-FX net cash change शी तुलना होत होती. IFRS IAS 7 पद्धतीनुसार आता दोन स्वतंत्र तपासण्या आहेत:
   - CFO + CFI + CFF = net cash movement before FX
   - pre-FX movement + exchange-rate effect = post-FX movement
2. `EffectOfExchangeRateChangesOnCashAndCashEquivalents` हा XBRL fact audit-only candidate म्हणून extract होतो.
3. Synthetic tests मध्ये zero FX, non-zero FX, SETCO-shaped ₹1.12 crore bridge, आणि missing pre-FX fact असताना fallback न होणे तपासले आहे.
4. 9M CFO fact नसेल तर Q4 CFO `WAIT_FOR_DATA` राहतो; कोणतीही अंदाजित Value तयार होत नाही.

## Local Validation (या patch मध्ये वापरलेल्या uploaded source archive वर)

- XBRL / Q4 focused tests: 63 PASS
- Mainboard + Delivery + Liquidity + Fundamental + Pipeline tests: 91 PASS
- V8 regression: 27 PASS
- Python compile: PASS
- पूर्ण `pytest -q`: timeout; full-suite PASS असा दावा नाही.

ही मोजणी वेगवेगळ्या test groups ची आहे; overlap असू शकतो.

## SETCO बद्दल महत्त्वाची नोंद

उपलब्ध जुन्या extracted XBRL facts मध्ये SETCO चा standalone FY context:
- CFO: -₹50.48 लाख
- CFI: ₹0
- CFF: ₹35.08 लाख
- pre-FX net change: -₹15.40 लाख
- reported post-FX net change: -₹15.40 लाख
- FX effect fact: उपलब्ध extracted CSV मध्ये नाही.

ही माहिती आधीच्या ₹1.12 कोटी mismatch च्या दुसऱ्या context शी एकसारखी नाही. त्यामुळे FX bridge हा संभाव्य तपासण्याचा मार्ग आहे; SETCO mismatch सुटला असे म्हणता येत नाही. मूळ XML पुन्हा fetch करून exact context, basis आणि FX fact तपासणे आवश्यक आहे.

## Safety

- कोणतेही Fundamental Cache values बदलत नाहीत.
- कोणताही XBRL fact `VERIFIED` होत नाही; सर्व `CANDIDATE_ONLY_NOT_VERIFIED` राहतात.
- Q4 CFO हा फक्त exact annual + 9M matched facts मिळाल्यास `DERIVED_Q4_CFO_CANDIDATE_ONLY`; अन्यथा `WAIT_FOR_DATA`.
- Master Specification, RVOL, Delivery A/B, Liquidity किंवा selection rules बदललेले नाहीत.
- GitHub push/deploy केलेले नाही.

## Base compatibility warning

शेवटच्या uploaded workflow log मध्ये checkout SHA `21505ad2541d5be6135ed84fc33697146cf75b8e` दिसतो. मात्र उपलब्ध `AI-Trading-Bot-main (3)(1).zip` मध्ये `fundamental_metric_verification.py` नाही, जरी त्या log च्या compile/test commands मध्ये तो आहे. म्हणून uploaded source archive आणि logged `main` हे byte-for-byte समान नाहीत. हा patch XBRL-संबंधित फाइल्सपुरता आहे; GitHub `main` वर लागू करण्यापूर्वी SHA `21505ad` मधील या पाच फाइल्सशी diff तपासणे आवश्यक आहे. `WORKFLOW_INSERT.yml` हा फक्त Q4 audit execution step साठी insertion snippet आहे; पूर्ण workflow replace करू नये.
