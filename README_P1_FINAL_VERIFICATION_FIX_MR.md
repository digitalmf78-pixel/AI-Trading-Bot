# NSE V8 — P1 Final Verification Fix (2026-10-31)

## उद्देश
P1 Cache Basis Persistence मधील stale provider refresh reset अधिक पूर्ण करणे आणि त्यासाठी targeted regression test जोडणे.

## बदल
`fundamental_data_provider.py` मध्ये 30-day stale provider-owned record refresh होताना जुने provider metrics सोबत खालील जुने metadata देखील clear केले जातात:
- `AsOfDate`, `DataRetrievedAtUTC`
- `Source`, `SourceURL`
- `FinancialPeriodEnd`, `PublicationDate`, `PublicationDateStatus`
- `OfficialFilingURL`, `OfficialFilingSource`
- `MetricPeriodAlignmentStatus`, `ProviderSector`
- calculation basis आणि सर्व ProviderFetch provenance fields

यानंतर नव्या provider fetch मधून उपलब्ध माहिती पुन्हा भरली जाते. `V8_FUNDAMENTAL_REFRESH_DAYS` चा default 30 दिवस कायम आहे. Manual/non-Yahoo records stale-provider refresh म्हणून clear होत नाहीत.

`test_fundamental_data_provider.py` मध्ये `test_stale_provider_refresh_clears_old_metrics_basis_and_provenance` जोडली आहे. ही test जुने metrics, basis, timestamps आणि official-filing metadata reset होतात का तसेच dated snapshot तयार होतो का हे तपासते.

## Local validation
- `test_fundamental_data_provider.py` + cache persistence + alignment + official filing suites: **37 PASS**
- Fundamental filter / fail-closed / pipeline order / liquidity / delivery suites: **34 PASS**
- एकूण: **71 PASS**
- Python compile: **PASS**

## मर्यादा
- हे local patch आहे; GitHub वर commit/push/deploy केलेले नाही.
- Reports artifact `nse-v8-reports-41098433437.zip` मध्ये `data/cache/fundamental_history/` directory नव्हती. त्यामुळे त्या artifact वरून GitHub वरचे dated history snapshot files थेट verify करता आले नाहीत.
- Workflow YAML मध्ये history directory git add/commit करण्याची configuration आहे आणि local history snapshot test PASS आहे; तरी GitHub runtime वर प्रत्यक्ष snapshot commit झाला आहे यासाठी commit diff किंवा पुढील run मधील checkout/history listing आवश्यक आहे.
- Master specification, RVOL, Delivery, liquidity, technical filters, Telegram आणि Quarterly TTM logic बदललेले नाही.

## Apply
या ZIP मधील दोन्ही Python files repository च्या root मध्ये त्याच नावाने replace करा. नंतर commit/push करून GitHub Actions चालवा. नवीन run logs आणि repository persistence commit तपासल्याशिवाय P1 ला Final PASS समजू नये.
