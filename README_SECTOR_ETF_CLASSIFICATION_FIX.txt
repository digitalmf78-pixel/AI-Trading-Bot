NSE V8 Sector ETF Classification Fix

Scope
- Adds an explicit, evidence-backed classification for ETF symbol VALUE.
- VALUE tracks the Nifty 500 Value 50 Total Return Index, which is a broad-market factor index, not one of the tracked Nifty sector indices. The bot therefore records it as ETF_UNDERLYING_INDEX_UNSUPPORTED instead of repeatedly treating it as a missing company-sector mapping.
- DIVIDEND remains unresolved because the exact scheme/underlying index has not been verified. It is intentionally not guessed.
- BEDMUTHA, JKIPL and AROGRANITE remain unmapped unless exact tracked-sector membership or an official classification that matches the existing taxonomy is found.

Files
- sector_data.py: complete replacement for the version supplied in NSE_V8_Sector_Mapping_Issuer_Fallback_Patch.zip, with only the VALUE ETF status added.
- test_sector_mapping_patch.py: regression tests including the new ETF case and safe no-guess checks.

Validation
Run: python -m unittest -v test_sector_mapping_patch.py
Run: python -m py_compile sector_data.py test_sector_mapping_patch.py

Important
This does not force sector mapping for unresolved symbols and does not change the Delivery Filter or Risk/Reward rules. GitHub Actions must be run after replacing the file; local tests are not proof that live NSE feeds are available.
