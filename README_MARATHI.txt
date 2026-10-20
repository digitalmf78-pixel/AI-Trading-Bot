NSE V8 HISTORY ENDPOINT CORRECTED FIX — 20-Oct-2026

नवीन लॉग logs_106811894344.zip मधील निरीक्षण:
- नवीन BackPage URL वापरला गेला होता, तरी live response मध्ये 6 सेक्टरसाठी NO_DATA आले.
- Refresh result: exact_date_sectors=17; 6 आवश्यक सेक्टरसाठी 19-Oct-2026 डेटा उपलब्ध नव्हता.
- याचा अर्थ आधीचा Route Fix live मध्ये समस्या सोडवू शकला नाही.
- लॉगमध्ये वापरलेला endpoint /BackPage/getHistoricaldatatabletoString आणि MM/DD/YYYY date format हे ऐतिहासिक API च्या documented contract शी जुळत नाहीत.

या Patch मध्ये फक्त:
1) sector_data.py — documented /Backpage.aspx/getHistoricaldatatabletoString endpoint आणि DD Mon YYYY date format.
2) test_nse_official_index_api.py — त्यानुसार regression expectations.

महत्त्वाचे:
- हा patch live API चालेल याची हमी नाही. GitHub Actions मधील पुढचा run हा live verification आहे.
- फक्त मुख्य AI-Trading-Bot repo मध्ये या दोन फाइल्स replace करा.
- delivery_filter.py, volume_gainer.py, News logic आणि स्वतंत्र Delivery Watchlist प्रोजेक्ट बदलू नका.
- Live response रिकामा/HTML राहिला तर डेटा अंदाजाने भरू नका; WAIT_FOR_DATA कायम ठेवा.
