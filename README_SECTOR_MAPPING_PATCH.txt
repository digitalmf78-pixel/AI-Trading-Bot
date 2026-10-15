NSE V8 Sector Mapping - focused issuer-evidence fallback patch

Files
- sector_data.py: complete replacement file, based on the uploaded AI-Trading-Bot-main(3).zip source.
- test_sector_mapping_patch.py: focused tests for the added fallback and fail-closed behavior.

Change
- Adds one reviewed, source-backed mapping for AMJLAND to the tracked Nifty Realty benchmark, based on AMJ Land Holdings' official website describing its current core business as Real Estate Development.
- Does NOT map AKASH or EFCIL; they remain WAIT_FOR_DATA because current source evidence does not justify assigning either to one of the module's tracked Nifty sector benchmarks.
- Keeps AONELIQUID and HDFCBSE500 unsupported as sector ETFs; does not guess their sector.
- Unknown symbols still remain WAIT_FOR_DATA.
- No RVOL, Delivery, shortlist, or other V8 modules are changed.

Local validation performed
- python -m py_compile sector_data.py: PASS
- python -m unittest -v test_sector_mapping_patch.py: 4/4 PASS

Important
This patch has NOT been applied to GitHub and has NOT been validated by a GitHub Actions run. The test file is a focused local regression test; it is not the full V8 regression suite.
