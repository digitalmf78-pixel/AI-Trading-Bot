# NSE V8 Fundamental Official Filing Endpoint Fix (2026-10-24)

## Root cause found from report `nse-v8-reports-40068447073.zip`

The live diagnostic CSV proves the current code queried the **general corporate-announcements endpoint**:
`https://www.nseindia.com/api/corporate-announcements`

It returned 229,239 general announcement records. The first matching records include subjects such as `Clarification - Financial Results`; their sample metadata has publication timestamps and symbols, but no populated attachment or financial period-end field. The current parser therefore reports 1,983 broad text matches and 0 period ends. This is not simply a date-format parsing problem: the feed is too broad for reliable financial-period metadata.

## What this patch changes

- Uses NSE's dedicated Integrated Filing - Financials endpoint as the primary source:
  `https://www.nseindia.com/api/integrated-filing-results`
- Requests `type=Integrated Filing- Financials`, `index=equities`, and the same bounded lookback window.
- Supports common filing-field aliases for symbol, broadcast/filing date, and period-end (`toDate`, `to_date`, `period_ended`, etc.).
- Captures endpoint, request parameters, response shape, sample keys/fields, rejection counts and errors in `outputs/v8_official_fetch_diagnostics.csv`.
- Keeps strict verification: no publication date or period-end is inferred from the EOD cutoff or another unrelated date.
- Does not substitute a generic NSE page as a filing-specific URL when no official attachment/XBRL URL is provided.
- Changes only `fundamental_official_filings.py` and its focused regression tests. No RVOL, Delivery, Liquidity, technical, sector, news, event, or risk rules are changed.

## Validation

- Focused Fundamental/Data Provider/Filter/Shortlist tests: **33 passed**
- Python compile: **PASS**
- Live NSE endpoint verification: **PENDING**. Tests use mocked responses, so apply this patch and run NSE Data Test before treating official filings as verified.

## Apply

Replace these two files in the repository with the files in this ZIP:
1. `fundamental_official_filings.py`
2. `test_fundamental_official_filings.py`

Commit/push and run the NSE Data Test workflow. Then upload the resulting report ZIP. Inspect `outputs/v8_official_fetch_diagnostics.csv` for `Endpoint`, `PayloadKeys`, `SampleMatchedItemKeys`, `SampleMatchedItemFields`, `PeriodEndParsed`, and `AcceptedRows`.

Do not mark records VERIFIED if the dedicated endpoint's actual payload does not provide a trustworthy symbol, filing/publication date, and financial period end.
