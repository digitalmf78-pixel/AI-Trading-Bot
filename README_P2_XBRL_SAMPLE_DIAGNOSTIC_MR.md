# NSE V8 — Official XBRL Sample Diagnostic (Diagnostic Only)

## Purpose
The current scanner records official NSE filing XML URLs in
`data/inputs/fundamental_metrics.csv`, and has a retrying allow-listed XML
downloader. This diagnostic connects those two existing components for one
controlled evidence-gathering run.

It selects up to five distinct, newest official NSE `.xml` filing URLs from
`OfficialFilingURL`, downloads them through `nse_xbrl_fetch.py`, and records:
- download success/failure and reason;
- XBRL root tag and namespace;
- context count, entity identifier, start/end/instant period details;
- unit count and unit measures;
- total fact count;
- preliminary Cash Flow-like tag count and sample facts with context/unit refs.

## Outputs
- `outputs/xbrl_sample_diagnostics/xbrl_sample_diagnostic.json`
- `outputs/xbrl_sample_diagnostics/xbrl_sample_diagnostic_summary.csv`
- `data/cache/xbrl_samples/*.xml` (raw downloaded samples)

The GitHub Actions artifact includes these outputs for inspection.

## Safety / scope
- Diagnostic only: does not change `fundamental_data_provider.py`, metric values,
  TTM calculations, annual fallback, fundamental thresholds, cache refresh policy,
  or any trading selection/filter.
- No XBRL fact is treated as verified financial data by this patch.
- Cash Flow tag matching is preliminary discovery, not a complete taxonomy map.
- No YTD-to-quarter subtraction or TTM calculation is performed.
- Download failures are retained per sample in the JSON report; this step is
  non-blocking for the scanner, but the diagnostic report must be reviewed.
- Only HTTPS URLs on the existing official NSE host allow-list ending in `.xml`
  are selected.

## Validation
Run:
`pytest -q test_nse_xbrl_fetch.py test_nse_xbrl_sample_diagnostic.py test_fundamental_data_provider.py test_fundamental_shortlist_and_alignment.py test_fundamental_official_filings.py`

This validates mocked XML parsing/report generation and downloader behavior.
It does not prove live NSE download success or correct XBRL taxonomy mapping.
