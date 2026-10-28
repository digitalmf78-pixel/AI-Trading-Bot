# NSE V8 — Targeted Official Filing Lookup (मराठी)

## हा patch कशासाठी आहे?

24-Oct-2026 च्या report मध्ये 204 candidates पैकी 169 `VERIFIED` आणि 35 `UNVERIFIED` होते. Bulk Integrated Filing dataset मध्ये काही candidate symbol + expected period-end जोड्या सापडत नव्हत्या. हा patch bulk dataset बदलून अंदाजाने `VERIFIED` करत नाही. तो फक्त exact match न सापडलेल्या candidate pairs साठी NSE Integrated Filing endpoint वर symbol-specific lookup करतो.

## काय बदलले?

- `fundamental_official_filings.py` मध्ये `_fetch_targeted_nse_filings()` helper जोडला.
- प्रत्येक unmatched candidate साठी expected Financial Period End पासून EOD cutoff पर्यंत NSE query केली जाते.
- आधी `index=equities`, exact symbol + period-end match न मिळाल्यास `index=sme` query केली जाते.
- response मध्ये `symbol`, `qe_Date` (period end) आणि `creation_Date` (publication/broadcast date) यांची पडताळणी केली जाते.
- फक्त exact symbol + period-end असलेला आणि EOD cutoff पर्यंतचा official publication date असलेला recordच `VERIFIED` होऊ शकतो.
- unresolved candidates `UNVERIFIED` राहतात; तारीख/period infer होत नाही.
- targeted lookup चे diagnostic status verification CSV मध्ये नोंदवले जाते आणि अतिरिक्त filing rows cache CSV मध्ये merge होतात.

## Tests

Mocked tests मध्ये equities मधील period mismatch नंतर SME fallback आणि unmatched candidate साठी targeted lookup वापरला जातो का हे तपासले आहे. हे tests live NSE API verification नाहीत.

## Apply करण्यापूर्वी

1. GitHub `main` मधील सध्याच्या `fundamental_official_filings.py` ची backup copy घ्या.
2. या ZIP मधील फाइल पूर्ण replacement म्हणून लागू करा.
3. संबंधित test suite चालवा.
4. GitHub Actions EOD workflow चालवून `v8_official_publication_date_verification.csv` आणि `v8_official_fetch_diagnostics.csv` तपासा.
5. Live result मध्ये exact match नसेल तर `UNVERIFIED` कायम ठेवा.

## Scope

हा patch फक्त official filing verification मध्ये targeted lookup जोडतो. RVOL, Delivery A/B, Liquidity, Technical, Sector, News, Risk किंवा trading thresholds बदलत नाही. GitHub वर patch लागू झालेला नाही; NSE live API वर परिणाम सिद्ध झालेला नाही.
