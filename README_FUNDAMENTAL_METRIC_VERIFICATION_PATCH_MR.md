# NSE V8 — Fundamental Metric-Level Official Verification Audit

## उद्देश
Fundamental cache मधील metric value आणि Official NSE filing metadata यांतील फरक स्पष्ट ठेवणे. NSE filing URL किंवा Publication Date `VERIFIED` असणे म्हणजे Yahoo/yfinance मधील Revenue, Profit, CFO, ROE किंवा इतर metric values अधिकृत XBRL शी जुळल्या आहेत असे मानले जाणार नाही.

## या Patch मधील बदल

1. `fundamental_metric_verification.py` जोडले आहे. हा read-only audit प्रत्येक non-empty numeric fundamental metric साठी स्वतंत्र verification row तयार करतो.
2. Filing metadata तपासणी आणि metric-value verification वेगवेगळी ठेवली आहे.
3. Metric ला `OFFICIAL_XBRL_VERIFIED` फक्त तेव्हाच दिले जाते जेव्हा evidence ledger मधील exact match आणि repository मधील XBRL XML यांचे SHA-256, fact tag, contextRef, entity identifier/scheme, period, dimensions, unit, taxonomy namespace आणि numeric value जुळतात.
4. सध्याच्या पहिल्या आवृत्तीत फक्त Annual Basis वरील `OperatingCashFlowINR` साठी `CashFlowsFromUsedInOperatingActivities` direct fact स्वीकारला आहे. ROE/ROCE/Debt-to-Equity/Interest-Coverage/Growth/FCF आणि TTM metrics साठी component-level calculation reconciliation लागते; ते `DERIVED_RECONCILIATION_REQUIRED` राहतात.
5. `data/inputs/fundamental_metric_verification_evidence.csv` हा रिकामा evidence template जोडला आहे. कोणताही metric evidence नसल्यास तो `PROVIDER_ONLY` राहतो.
6. Scheduled workflow मध्ये audit आणि regression tests जोडले आहेत. Output reports artifact मध्ये येतील आणि evidence ledger repository persistence मध्ये stage होईल.

## सुरक्षितता
- `fundamental_metrics.csv` मधील कोणतीही value बदलली/overwrite केली जात नाही.
- जुन्या snapshots मध्ये बदल होत नाही.
- Delivery A/B, RVOL, Liquidity, Technical, Entry/Exit किंवा Risk rules बदललेले नाहीत.
- Fundamental collection हा pipeline मधील candidate rejection gate बनत नाही. Verification status स्वतंत्र audit output आहे.
- Filing metadata match म्हणजे metric verified असा अर्थ काढला जात नाही.

## सध्याच्या Uploaded Snapshot वर अपेक्षित अर्थ
सध्याच्या cache मधील `Source` Yahoo Finance via yfinance आहे आणि metric-level official XBRL evidence ledger रिकामा आहे. त्यामुळे populated numeric metrics `PROVIDER_ONLY` म्हणून दाखवले जातील. हीच सुरक्षित आणि पुराव्याशी सुसंगत स्थिती आहे; हा audit कोणतेही value आपोआप promote करत नाही.

## Validation
Targeted unit tests खालील बाबी तपासतात: filing metadata ≠ metric verification, exact direct-fact verification, provider value mismatch, SHA mismatch, derived metric hold, dimension mismatch, आणि cache non-mutation.

## मर्यादा
हा audit engine आणि evidence contract जोडतो; तो 364 records साठी स्वतःहून सर्व XBRL XML डाउनलोड करून derived metrics ची गणना करत नाही. त्या कामासाठी पुढील टप्प्यात annual/quarterly statement component mapping आणि period/basis-aware reconciliation आवश्यक आहे. त्यामुळे हा patch एकट्याने संपूर्ण Fundamental Data ला verified बनवत नाही.

## 03-Nov-2026 uploaded source snapshot मधील प्रत्यक्ष audit निकाल

Uploaded repository snapshot SHA header: `5a8dbd926c7f42f83012d4fcf2e5e249eb4d230c` (ZIP मध्ये `.git` metadata नाही; त्यामुळे हा archive header/reference आहे, live GitHub HEAD ची स्वतंत्र पुष्टी नाही).

- Fundamental cache records: **364 symbols**
- Populated numeric metric rows audited: **2,734**
- Metric-level XBRL evidence ledger: रिकामा
- Metric-value verification: **2,734 `PROVIDER_ONLY`; 0 `OFFICIAL_XBRL_VERIFIED`**
- Exact official filing metadata match: **296 symbols**
- Official filing URL missing: **67 symbols**
- Exact symbol/period/URL filing row not found: **1 symbol — ABCOTS**

ABCOTS साठी cache मध्ये FY period `2026-03-31` आणि publication date `2026-05-27` आहे, पण या ZIP मधील official filing register मध्ये त्या symbol/period साठी कोणतीही row सापडली नाही. त्यामुळे हा record स्वतंत्रपणे resolve होईपर्यंत त्याचे filing metadata match झालेले मानायचे नाही.

वरील 296 match हे फक्त filing metadata match आहेत. त्यांना 2,734 metric values चे XBRL verification समजू नये.

### Metric-level status breakdown (2,734 populated metric rows)

- `DERIVED_RECONCILIATION_REQUIRED`: **2,056** rows across 296 symbols (growth/ratios/FCF/TTM are not eligible for one-fact verification).
- `FILING_METADATA_NOT_CONFIRMED`: **526** rows across 68 symbols (67 missing filing URLs and ABCOTS exact filing-register mismatch).
- `PROVIDER_ONLY`: **152** rows across 152 symbols (annual OCF values have no metric-level XML evidence row).
- `OFFICIAL_XBRL_VERIFIED`: **0** rows.

This classification deliberately does not treat an official filing link as proof of a Yahoo metric. Only annual OCF is eligible for the current direct-fact path; all other metrics need component-level reconciliation.
