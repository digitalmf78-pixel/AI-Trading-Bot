# NSE V8 – Targeted Filing Lookup Diagnostic Hardening

## काय दुरुस्त केले

`fundamental_official_filings.py` मधील targeted lookup diagnostics मध्ये एक reporting defect होता:
- candidate च्या requested FinancialPeriodEnd पेक्षा वेगळ्या period ची filing मिळाली तरी `RowsAccepted` मध्ये ती मोजली जात होती.
- त्यामुळे `RowsAccepted` हा आकडा exact symbol + exact period match दर्शवत नव्हता.

आता diagnostics मध्ये:
- `RowsReturnedInWindow`: त्या symbol साठी परत आलेल्या eligible filing rows.
- `RowsRejectedPeriodMismatch`: requested period पेक्षा वेगळ्या period च्या rows.
- `RowsAccepted`: फक्त requested exact period-end शी जुळणाऱ्या rows.

इतर period च्या rows shared filings cache मध्ये राहू शकतात; मात्र त्या requested candidate साठी accepted match म्हणून मोजल्या जाणार नाहीत. Exact symbol + exact period + cutoff आधीची publication date ही verification अट बदललेली नाही.

## Test

Focused fundamental tests:
`45 passed`

पूर्ण repository `pytest -q` चालवण्याचा प्रयत्न केला; environment timeout झाल्यामुळे full-suite निकाल उपलब्ध नाही. त्यामुळे full suite pass झाल्याचा दावा नाही.

## महत्त्वाची मर्यादा

हा patch targeted lookup च्या diagnostics मधील चुकीची acceptance count दुरुस्त करतो. तो NSE API मधून न मिळालेल्या 31 exact symbol-period filings स्वतःहून शोधत नाही आणि कोणत्याही stock ला VERIFIED/PASS करत नाही. त्या 31 pairs साठी exact match अजून unresolved आहे.

Master specification, RVOL, Delivery A/B, thresholds किंवा इतर modules बदललेले नाहीत.
