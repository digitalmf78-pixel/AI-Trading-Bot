# NSE V8 P2 – Official Annual / 9M Cash Flow Audit Patch

## या Patch मध्ये काय आहे?

1. `nse_xbrl_ytd_cashflow_reconciliation.py` – Official NSE annual filing आणि त्याच कंपनीच्या त्याच Standalone/Consolidated basis च्या 9-month YTD filing मधून CFO candidate तपासतो.
2. `test_nse_xbrl_ytd_cashflow_reconciliation.py` – pair selection, same-basis check, entity/unit/dimension validation आणि derived Q4 candidate tests.
3. `NSE_V8_P2_Q4_CFO_WORKFLOW.patch` – नवीन audit step, compile/test integration आणि artifact upload.
4. `NSE_V8_PUBLICATION_DIAGNOSTIC_LABEL_FIX.patch` – previously verified ABCOTS सारख्या cache row ला diagnostic मध्ये चुकीचे `UNVERIFIED` दाखवण्याऐवजी `PRESERVED_PREVIOUSLY_VERIFIED` दाखवतो.

## नवीन CFO audit कसा काम करतो?

- Fundamental cache मधील `LEGACY_CACHE_BASIS_UNKNOWN` records निवडतो.
- त्या record चा exact annual `OfficialFilingURL` official filings index मध्ये match करतो.
- त्याच Symbol आणि त्याच Standalone/Consolidated basis चा 9M filing (`FinancialPeriodEnd = annual period end - 3 months`) शोधतो.
- दोन्ही XML मध्ये Symbol identity, exact fiscal start/end, reporting basis, entity identifier/scheme, taxonomy namespace, INR unit आणि undimensioned CFO fact जुळले पाहिजेत.
- मगच `Annual CFO - 9M YTD CFO` ही Q4 CFO candidate गणना करतो.
- निकाल `DERIVED_CANDIDATE_ONLY_NOT_VERIFIED` राहतो.

## उपलब्ध uploaded artifact मधून pair inventory

EOD cutoff 2026-11-02 च्या report वरून:

- Legacy/unknown basis records: 173
- Same-basis FY annual + 9M filing pairs: 134
- Verified annual filing असून same-basis 9M filing न सापडलेले: 4
- Annual URL missing/unverified किंवा FY annual period शी न जुळलेले: 30
- March FY annual period नसलेले: 5

पहिल्या run मध्ये फक्त 5 priority symbols तपासले जातील: SETCO, NIRAJ, LAL, DONEAR, DNAMEDIA. Pair inventory `NSE_V8_P2_Q4_CFO_AUDIT_EVIDENCE_2026-11-03.zip` मध्ये आहे.

## Apply करण्याची पद्धत

Repository root मधून:

1. या ZIP मधील दोन्ही `.py` files repository root मध्ये copy करा.
2. `NSE_V8_PUBLICATION_DIAGNOSTIC_LABEL_FIX.patch` आणि `NSE_V8_P2_Q4_CFO_WORKFLOW.patch` repository root मध्ये ठेवा.
3. आधी current `main` वर dry-run करा:

```bash
git status --short
git apply --check NSE_V8_PUBLICATION_DIAGNOSTIC_LABEL_FIX.patch
git apply --check NSE_V8_P2_Q4_CFO_WORKFLOW.patch
```

4. दोन्ही checks pass झाल्यावर apply करा:

```bash
git apply NSE_V8_PUBLICATION_DIAGNOSTIC_LABEL_FIX.patch
git apply NSE_V8_P2_Q4_CFO_WORKFLOW.patch
```

5. Tests:

```bash
python -m pytest -q test_fundamental_official_filings.py test_fundamental_data_provider.py test_fundamental_shortlist_and_alignment.py test_fundamental_fail_closed.py
python -m pytest -q test_nse_xbrl_ytd_cashflow_reconciliation.py test_nse_xbrl_statement_reconciliation.py test_nse_xbrl_financial_fact_audit.py test_nse_xbrl_sample_diagnostic.py test_nse_xbrl_fetch.py
python -m py_compile nse_xbrl_ytd_cashflow_reconciliation.py test_nse_xbrl_ytd_cashflow_reconciliation.py
```

6. Commit/push केल्यानंतर `NSE Data Test` workflow run करा आणि `outputs/xbrl_ytd_cashflow_reconciliation/` तपासा.

## Local validation

- New Q4 CFO audit tests: 5 PASS
- Combined focused regression set: 61 PASS
- Python compile: PASS
- Workflow YAML parse: PASS
- Patch dry-run/apply against the supplied integrated workflow/source baseline: PASS
- Synthetic end-to-end run: 1 pair -> 1 derived candidate; no cache write
- Full `pytest -q` did not complete within the local execution time limit; त्यामुळे full-suite PASS असा दावा नाही.

## Safety / काय बदलत नाही?

- `fundamental_metrics.csv` किंवा dated history snapshots बदलत नाही.
- कोणताही CFO, Revenue, Net Profit किंवा TTM value cache मध्ये लिहीत नाही.
- कोणताही value `VERIFIED` करत नाही.
- Fundamental Score, RVOL, Delivery A/B, Liquidity, Technical/Risk filters बदलत नाही.
- Master Specification बदलत नाही.
- XBRL fetch/parse/reconciliation failure non-blocking diagnostic म्हणून नोंदवली जाते; report status manually पाहणे आवश्यक आहे.

Patch हा उपलब्ध checkout `3eda7e6` च्या integrated XBRL workflow baseline वर तयार केला आहे. Latest `main` वर apply करण्यापूर्वी `git apply --check` अनिवार्य आहे. GitHub वर push/deploy केलेले नाही.
