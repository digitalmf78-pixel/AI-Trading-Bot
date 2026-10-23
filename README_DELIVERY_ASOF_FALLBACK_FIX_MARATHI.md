# NSE V8 — Delivery Report Availability Fix (23 Oct 2026)

## समस्या
23-10-2026 चा price bhavcopy उपलब्ध होता; पण त्याच तारखेचा delivery report HTTP 404 देत होता. `delivery_filter.py` मध्ये as-of तारखेचा report नसल्यास लगेच `WAIT_FOR_DATA` देत असल्याने जुन्या वैध delivery reports तपासले जात नव्हते. त्यामुळे Delivery A/B आणि Fundamental Collection शून्य rows वर थांबत होते.

## बदल
- As-of report उपलब्ध नसेल तर स्पष्ट diagnostic नोंदवून मागील तारखांचे reports तपासले जातात.
- फक्त 5 वेगवेगळ्या, वैध report dates वापरल्या जातात.
- पाच reports उपलब्ध नसल्यास अजूनही `WAIT_FOR_DATA` राहते.
- जुन्या delivery data ला as-of date म्हणून दाखवले जात नाही. Audit मध्ये `DeliveryAsOfDate`, `DeliveryAsOfReportAvailable`, `DeliveryWindowStartDate`, `DeliveryWindowEndDate` दिले जातात.
- `LatestDeliveryPct` हा निवडलेल्या विंडोतील शेवटच्या वैध report date चा आकडा असतो.
- Category A: 5-session average >= 60.00%; Category B: प्रत्येक दिवस >= 60.00%. विद्यमान नियम कायम.
- GitHub Actions workflow मध्ये नवीन regression tests जोडले.

## GitHub वर लागू करणे
ZIP मधील paths जसेच्या तसे repository मध्ये copy/replace करा, commit/push करा आणि `NSE Data Test` workflow चालवा.

## Safety
हा patch missing report ला PASS समजत नाही. पाच valid distinct sessions न मिळाल्यास `WAIT_FOR_DATA` राहते. Live NSE availability या offline tests मध्ये simulate केली आहे; पुढील GitHub Actions log मध्ये actual report availability आणि counts verify करणे आवश्यक आहे.
