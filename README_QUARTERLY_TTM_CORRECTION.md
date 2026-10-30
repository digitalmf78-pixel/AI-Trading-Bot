# NSE V8 Quarterly Fundamental Alignment — Corrected TTM Patch

This patch replaces the earlier quarterly calculation that annualized a single quarter by multiplying by four.

## Calculation rules
- Revenue and profit growth: latest quarter versus the same quarter one year earlier (requires five income-statement columns).
- ROE: four-quarter TTM net income divided by latest reported equity; average equity is used only when the previous-quarter balance-sheet value is present.
- ROCE: four-quarter TTM EBIT divided by latest reported capital employed (total assets less current liabilities).
- Interest coverage: four-quarter TTM EBIT divided by four-quarter TTM interest expense.
- Operating cash flow and free cash flow: sum of four aligned quarters. FCF falls back to TTM OCF plus TTM capex only when all four capex quarters are available.
- Income and cash-flow statement quarter ends must align across the latest four quarters; balance sheet must match the latest quarter. Otherwise quarterly alignment fails closed and existing annual fallback remains available.
- Quarterly values are provider-derived secondary data. Official filing/publication verification remains a separate gate; no automatic PASS is granted.

## Scope safeguards
No changes to Master Specification, RVOL, Delivery A/B, 30-day refresh, liquidity, technical filters, or trading gates. Apply only after reviewing regression results.
