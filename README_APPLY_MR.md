# NSE V8 — Fundamental Status Hardening (29-Oct-2026)

## काय बदलले?
1. `FundamentalReason` मध्ये `DUPLICATE_FUNDAMENTAL_RECORDS` असल्यास stock ला चुकीने PASS मिळणार नाही; तो `WAIT_FOR_DATA` राहील.
2. `FundamentalShortlistStatus` आणि `FundamentalAssessmentStatus` हे दोन्ही public status fields shortlist function मधून sync ठेवले जातील.
3. त्याचप्रमाणे reason fields सुद्धा sync राहतील.
4. Master specification, RVOL, Delivery A/B thresholds किंवा इतर trading filters बदललेले नाहीत.

## Validation
Latest extracted source tree (`AI-Trading-Bot-main (15).zip` मधून) वर patch apply करून focused tests चालवले:

`python -m pytest -q test_fundamental_shortlist_and_alignment.py test_fundamental_filter.py test_fundamental_fail_closed.py test_fundamental_official_filings.py test_fundamental_data_provider.py test_fundamental_cache_persistence_workflow.py`

Result: **46 passed in 0.49s**.

## महत्त्वाची मर्यादा
हा patch फक्त local extracted copy वर लागू व test केला आहे. तो GitHub repository वर push/commit केलेला नाही. GitHub मध्ये upload/commit केल्यानंतर scheduled workflow चालवून reports आणि cache commit तपासणे आवश्यक आहे. हा patch official filings मधील missing numeric metrics आपोआप भरत नाही आणि unverified filing ला VERIFIED करत नाही.

## Apply
ZIP मधील `.patch` file matching repository root मधून apply करा. GitHub web UI वापरत असल्यास `fundamental_shortlist.py` आणि `test_fundamental_shortlist_and_alignment.py` मधील बदल तपासून commit करा. Master spec file बदलू नका.
