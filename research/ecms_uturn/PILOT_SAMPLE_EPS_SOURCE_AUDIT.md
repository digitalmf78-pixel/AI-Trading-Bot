# U-Turn Pilot Sample — Annual Diluted EPS Source Audit

**Status:** Values checked against official issuer / NSE filing sources on 2026-11-17.
**Basis:** Consolidated, annual diluted EPS, INR/share, FY2025 vs FY2026.
**Scope:** This validates the two EPS numbers per issuer only. It does not independently validate every note, restatement, corporate action, or event timestamp.

| Symbol | FY2025 diluted EPS | FY2026 diluted EPS | Result | Official source |
|---|---:|---:|---|---|
| INFY | ₹64.34 | ₹71.46 | NO_EPS_DECLINE | [Infosys audited consolidated FY26 results](https://www.infosys.com/investors/documents/exchange-filings/2026/advertisement-pertaining-financial-results-q4fy26.pdf) |
| ACI | ₹13.12 | ₹8.65 | EPS_DECLINE | [Archean Chemical FY25-26 Annual Report — Note 32, Basic and Diluted EPS](https://www.archeanchemicals.com/investor-relations/admin/assets/products/ACIL%20Annual%20Report%2025-26.pdf) |
| AARTIIND | ₹9.12 | ₹11.55 | NO_EPS_DECLINE | [NSE iXBRL annual results filing](https://nsearchives.nseindia.com/corporate/ixbrl/INTEGRATED_FILING_INDAS_155487_04052026201324_iXBRL_WEB.html) and [NSE annual report](https://nsearchives.nseindia.com/annual_reports/AR_30737_AARTIIND_2025_2026_A_22486837_27082026184733.pdf) |

## Interpretation

- The sample contains one EPS-decline event (ACI) and two no-decline controls (INFY, AARTIIND).
- These three stocks were already selected for the pilot; this is **not a randomized sample**. It must not be represented as unbiased or statistically representative.
- The event-study outputs are still provisional: corporate-action reconciliation and independent NSE calendar/session verification remain open.
- The 21/63/126-session outcomes describe post-result price behaviour, not trade returns.
- No entries, exits, position sizing, stop loss, fees, slippage, or P&L simulation are performed.
