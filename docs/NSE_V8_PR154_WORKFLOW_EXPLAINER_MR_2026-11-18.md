# NSE Swing Trading V8 — PR #154 Workflow Update (Marathi)
**दिनांक:** 18-11-2026  
**स्थिती:** PR #154 वर code CI PASS (पूर्वीच्या code head वर); NSE public calendar page वर live entries दिसतात; API JSON/schema आणि matching runtime audit बाकी; PR अजून Draft/Open आहे.  
**Branch:** `fix/nse-v8-official-nifty-history-2026-11-18`

> हा दस्तऐवज PR #154 मधील बदल समजावण्यासाठी स्वतंत्र workflow note आहे. **Master Specification बदललेली नाही आणि immutable राहील.**

## 1. EOD workflow कसा चालेल?

1. **Existing data/cache restore:** GitHub Actions मध्ये आधीचा Bhavcopy, Delivery, sector आणि fundamental संबंधित cache restore होतो. Bhavcopy चा 200-session history आणि Delivery reports चा विद्यमान cache workflow जसाच्या तसा राहतो.
2. **Bhavcopy / Mainboard universe:** NSE EOD Bhavcopy मधून stock rows घेतले जातात; अधिकृत Mainboard classification लागू होते. ETF/mutual-fund units वगळण्याचे विद्यमान नियम कायम.
3. **नवीन Official Financial Results Universe gate:** NSE च्या अधिकृत Event Calendar मधून Financial Results event dates घेतल्या जातात. सध्याच्या Mainboard/Bhavcopy cohort शी Symbol जुळवून **आजपासून पुढील 3 calendar months** मध्ये अधिकृतपणे घोषित Results date असलेलेच stocks पुढील Track 1 scanner मध्ये जातात. हा नवीन universe eligibility gate आहे.
4. **Results Priority — फक्त क्रम/दाखवण्याची प्राथमिकता:**
   - **P1:** आजपासून 1 calendar month पर्यंत.
   - **P2:** 1 ते 2 calendar months.
   - **P3:** 2 ते 3 calendar months.
   - P1 नसले तरी P2/P3 stocks बाद होत नाहीत. Priority मुळे Delivery/Liquidity/Fundamental/Technical नियम बदलत नाहीत.
5. **Delivery A/B:** उपलब्ध अधिकृत NSE Delivery reports चा 30-calendar-day window एकदाच fetch करून reuse होतो. किमान 5 valid distinct reports आवश्यक. Category A आणि B स्वतंत्रपणे तपासले जातात; पूर्ण A OR B union पुढे जातो. अपुरा/अवैध data म्हणजे WAIT_FOR_DATA.
6. **RVOL classification:** Delivery A/B union तयार झाल्यावर prior 20 full sessions च्या volume baseline वर RVOL मोजला जातो. RVOL >1.5 हा HIGH classification आहे; **RVOL <=1.5 किंवा RVOL unavailable म्हणून stock reject होत नाही.**
7. **Liquidity:** विद्यमान Liquidity filter लागू होतो (सध्याचा threshold ₹1.5 Cr). Reject/WAIT rows साठी पुढील Fundamental data fetch केला जात नाही.
8. **Fundamentals आणि पुढील विद्यमान analysis:** Liquidity नंतर विद्यमान fundamental enrichment/ranking, technical layers, news catalyst, sector/market context, risk checks, watchlists आणि signal-history/outcome tracking चालू राहतात. या PR मुळे त्यांचे thresholds किंवा निर्णय नियम बदललेले नाहीत.
9. **Research-only observations:** Accumulation, VCP/base आणि breakout/pullback observations अहवाल/Telegram मध्ये दिसू शकतात. त्या स्वतः BUY/ENTRY signal नाहीत.
10. **Reports:** Results universe audit आणि counts `outputs/` मध्ये लिहिले जातात. P1/P2/P3 आणि eligible next-3-month company counts console/report मध्ये दिसतात.\n11. **Track 2:** Full official Mainboard cohort चा snapshot Results gate च्या आधी घेतला जातो; Track 2 research observer Results eligibility मुळे कमी होत नाही. Track 1 मात्र Results-qualified cohort वरच पुढे जातो.

## 2. PR #154 मध्ये नेमके कोणते बदल केले?

| विभाग | बदल |
|---|---|
| Financial Results Universe | अधिकृत NSE calendar वर आधारित पुढील 3 calendar months cohort जोडला |
| Mainboard matching | NSE Results symbols आणि सध्याचा Mainboard/Bhavcopy cohort intersect केला |
| Priority | P1/P2/P3 labels आणि priority rank जोडले; हे display/order priority आहे, अतिरिक्त technical gate नाही |
| Fail-closed | Official calendar fetch/parse/verify अयशस्वी झाल्यास Track 1 input रिकामा करून WAIT_FOR_DATA audit लिहिला; full Mainboard fallback नाही |
| Nifty 50 history | Official NSE all-indices archive ला आधी प्राधान्य; स्वतंत्र `data/cache/market_index/` cache; existing Yahoo fallback कायम |
| Telegram research visibility | Valid research-stage accumulation/base/VCP/breakout/pullback observations दाखवणे; BUY/ENTRY म्हणून promote नाही |
| CI | Results universe आणि संबंधित tests CI मध्ये जोडले |

## 3. कोणते नियम/भाग बदललेले नाहीत?

- Master Specification — **बदललेली नाही**.
- Delivery A/B thresholds आणि त्यांचा क्रम — बदललेला नाही.
- Liquidity threshold — बदललेला नाही.
- RVOL हा classification-only नियम — बदललेला नाही.
- Fundamentals, News, Sector, Events, Deals, Technical आणि Risk logic — बदललेले नाहीत.
- Bhavcopy cache `data/bhavcopy/` आणि Delivery cache `data/cache/delivery/` — Results module त्यांना बदलत नाही.
- EOD workflow schedules/triggers — बदललेले नाहीत.
- ECMS workflow — या कामात मुद्दाम बदललेला नाही.

## 4. Schedule

विद्यमान `.github/workflows/nse-test-scheduled.yml` वेळा कायम:
- **EOD scan:** 16:40 UTC = **22:10 IST**, सोमवार–शुक्रवार.
- **Premarket refresh:** 02:30 UTC = **08:00 IST**, सोमवार–शुक्रवार.

## 5. नवीन Results reports

- `outputs/v8_results_universe_audit_YYYYMMDD.csv`
- `outputs/v8_results_universe_monthly_counts_YYYYMMDD.csv`

Audit मध्ये Mainboard symbol, Results-universe status, official results date आणि P1/P2/P3 priority यांची माहिती असते. Monthly summary मध्ये मागील महिना, चालू महिना, पुढील महिना आणि पुढील 3 महिन्यांचे distinct-company counts असतात.

## 6. महत्त्वाची मर्यादा / Merge पूर्वीची तपासणी

- Latest PR head: `28fb14514e7cdd833b6127aa73c490ee1baacb86`.
- Latest NSE V8 PR CI run: **44259914882 — SUCCESS** (compile, unit/data-audit, V8 regression आणि sector/news/official-index tests).
- **NSE ची अधिकृत Event Calendar webpage live तपासली: Financial Results purpose असलेले entries आणि dates दिसतात.** मात्र code मधील `/api/event-calendar` endpoint चा exact live JSON payload/schema, pagination/date-window coverage आणि त्याच वेळच्या Mainboard symbol matching प्रत्यक्ष scanner runtime मध्ये अजून verify झालेले नाहीत. Webpage render दिसणे म्हणजे API integration पूर्णपणे प्रमाणित झाले असे नाही.
- त्यामुळे PR Draft/Open ठेवायचा; Live audit पूर्ण होईपर्यंत Merge नाही.
- Live audit मध्ये API response schema, date range, Financial Results purpose matching, cancellations, duplicate symbols आणि Mainboard intersection तपासणे आवश्यक. Track 2 snapshot placement साठी regression test जोडला.

## 7. Workflow flow — एका ओळीत

**Bhavcopy → Official Mainboard → (Track 2 full-Mainboard snapshot) → Track 1: Official NSE Results (next 3 calendar months; P1/P2/P3 priority) → Delivery A/B → RVOL classification → Liquidity → Fundamentals → Technical/Risk → News/Sector context → Watchlists/Research reports → Signal history & outcomes.**

**टीप:** Track 2 चा input आता Results filter च्या आधी snapshot होतो; त्यामुळे तो full official Mainboard cohort वर चालतो. Results gate फक्त Track 1 scanner input कमी करतो.
