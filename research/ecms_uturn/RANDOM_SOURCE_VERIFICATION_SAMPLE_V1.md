# Random Source-Verification Sample V1 — Method and EPS Findings

This is a **source-verification pilot**, not a completed event-study.

## Sampling frame and rule

- Universe snapshot: 906 symbols in the ECMS fundamental-metrics cache.
- Candidate frame: 237 rows labelled COMPLETE_FIELDS_PROVENANCE after the seven numeric core metrics and per-metric source/URL/period/basis/currency metadata checks.
- The 237 rows do not mean the underlying seven metric facts have been independently verified; the audit explicitly leaves XBRL fact-level verification open.
- Sort the candidate symbols alphabetically, then draw five without replacement using Python's random.Random(20261117).sample(sorted_symbols, 5).
- Selected symbols, in order: UNITDSPR, INSPIRISYS, BORANA, KEYFINSERV, JSWSTEEL.
- Keep all selected symbols and data failures. No replacements after observing EPS or price outcomes.

The exact machine-readable selection record is [RANDOM_SOURCE_VERIFICATION_SAMPLE_V1.csv](RANDOM_SOURCE_VERIFICATION_SAMPLE_V1.csv).

## Annual diluted EPS evidence

| Symbol | FY2025 | FY2026 | Basis | Status |
|---|---:|---:|---|---|
| UNITDSPR | ₹22.28 | ₹25.89 | Consolidated, total diluted EPS | No decline |
| INSPIRISYS | ₹8.01 | ₹10.35 | Consolidated, diluted EPS | No decline |
| BORANA | ₹20.14 | ₹24.35 | Standalone, diluted EPS | EPS values found; ISIN discrepancy blocks price study |
| KEYFINSERV | — | — | — | WAIT_FOR_DATA; annual diluted EPS not verified |
| JSWSTEEL | ₹14.32 | ₹91.25 | Consolidated, total diluted EPS | No decline; FY26 contains material exceptional gain |

### Official source notes

- UNITDSPR: issuer's audited FY26 consolidated results dated 14 May 2026. The disclosed diluted EPS components are continuing operations ₹24.07 and discontinued operations ₹1.82 for FY26, and ₹20.35 plus ₹1.93 for FY25. Total diluted EPS is ₹25.89 and ₹22.28. [Official issuer filing](https://www.diageoindia.com/~/media/Files/D/Diageo-V2/Diageo-India/news-and-media/press-release/2026/diageo-india-audited-financial-results-for-the-quarter-and-financial-year-ended-31-march-2026.pdf).
- INSPIRISYS: NSE annual report note 32 states basic and diluted EPS from continuing and discontinued operations of ₹10.35 for FY26 and ₹8.01 for FY25. The annual audited consolidated result was approved on 8 May 2026. [NSE annual report](https://nsearchives.nseindia.com/annual_reports/AR_29350_INSPIRISYS_2025_2026_A_3995367_05062026135710.pdf) · [NSE result filing](https://nsearchives.nseindia.com/corporate/ixbrl/INTEGRATED_FILING_INDAS_156358_08052026184729_iXBRL_WEB.html).
- BORANA: NSE audited standalone results dated 14 May 2026 disclose diluted EPS of ₹24.35 FY26 and ₹20.14 FY25. However, the filing's header ISIN appears as INE16SF010106 while the NSE iXBRL security record identifies INE16SF01016. Treat the symbol/security identity as unresolved until reconciled. [NSE audited results](https://nsearchives.nseindia.com/corporate/BORANA_14052026182339_BM_Outcome.pdf) · [NSE iXBRL security record](https://nsearchives.nseindia.com/corporate/ixbrl/INTEGRATED_FILING_INDAS_208369_02112026185540_iXBRL_WEB.html).
- JSWSTEEL: NSE consolidated annual results show diluted EPS continuing plus discontinued operations of ₹91.25 FY26 and ₹14.32 FY25. FY26 includes a material exceptional gain; no adjusted EPS substitution has been made. [NSE iXBRL annual results](https://nsearchives.nseindia.com/corporate/ixbrl/INTEGRATED_FILING_INDAS_157679_14052026193924_iXBRL_WEB.html) · [NSE results presentation](https://nsearchives.nseindia.com/corporate/jessydenny_14052026164431_JSW_Steel_Q4_FY26_vF.pdf).
- KEYFINSERV: no accepted official annual diluted EPS pair was verified in this pass. Third-party/basic EPS is not substituted.

## Sampling outcome and implication

This random draw yielded three source-verified no-EPS-decline controls, one EPS pair with an unresolved security identifier, and one failed-data case. It yielded **zero verified EPS-decline cases**. That is a valid sample outcome and must be retained; it is not permission to redraw until an EPS-decline stock appears.

No U-Turn target is calculated for these five names in this report. The event-study requires a separately verified 20-session pre-result peak, exact result timing, corporate-action reconciliation, and price/delivery coverage. The current cache reconciliation gate for the earlier three-symbol pilot must pass before any price study is promoted.
