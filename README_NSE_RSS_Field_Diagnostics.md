# NSE V8 — Official RSS Field Diagnostics Patch

## Purpose

The latest workflow log shows that both official NSE RSS feeds fetched successfully, but the strict issuer matcher found zero official matches. The log currently records counts and match events, not a sample of the actual XML item fields. This patch adds bounded diagnostic samples of the first three items from each official feed so the next run reveals the actual RSS field shape (`title`, `description`, `link`, dates, and any other text fields).

## Scope and safety

- `news_catalyst.py` is a complete replacement file.
- Matching rules, delivery >= 60% gate, setup gate, source classification, and Mandatory 3+1 rules are unchanged.
- RSS sample logging is diagnostic only. It does not create news evidence or turn an unmatched item into a match.
- Each feed logs at most three sample items; each sample is bounded to 12 fields and 180 characters per field.
- Missing/unsupported news remains missing; no news is fabricated.

## Tests

Run:

```bash
python -m py_compile news_catalyst.py test_news_rss_diagnostics.py test_news_issuer_matching.py
python -m unittest -v test_news_issuer_matching.py test_news_rss_diagnostics.py
```

After commit, run the existing NSE workflow. In the log, inspect `[NEWS-DIAG] OFFICIAL_FEED_SAMPLE` before deciding whether any matching change is justified.
