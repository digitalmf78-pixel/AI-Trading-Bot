# NSE V8 P2 XBRL diagnostic artifact follow-up

## Purpose
This diagnostic-only follow-up makes the downloaded official NSE XML samples available in the GitHub Actions report artifact and captures XBRL context dimensions needed for later Standalone/Consolidated analysis.

## Changes
- Add `data/cache/xbrl_samples/` to the existing NSE report artifact upload paths.
- Record entity identifier scheme and XBRL explicit/typed dimensions for each context.
- Record fact namespace, scale, and sign attributes.
- Retain up to 200 cash-flow candidate facts per filing so candidate evidence is not silently truncated at 30.
- Add a unit test for context-dimension extraction.

## Safety / scope
- Does not calculate or overwrite financial metrics.
- Does not mark any fact or TTM value VERIFIED.
- Does not change the Fundamental Provider, scanner, cache refresh rules, delivery/RVOL/liquidity filters, Fundamental Score, or master specification.
- The raw XML files are official public filing data and are included only in the run artifact for inspection.
- The existing workflow diagnostic remains non-blocking; inspect the report and XML files rather than treating a green scanner as proof of financial verification.

## Apply
Merge the changed files into the current repository revision only after checking for workflow conflicts:
- `nse_xbrl_sample_diagnostic.py`
- `test_nse_xbrl_sample_diagnostic.py`
- `.github/workflows/nse-test-scheduled.yml`
