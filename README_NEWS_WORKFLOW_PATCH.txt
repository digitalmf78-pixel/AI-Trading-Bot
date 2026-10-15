NSE V8 — Standalone News Matching GitHub Actions Workflow

Add this new file to the repository at:
  .github/workflows/news-matching-tests.yml

The workflow is intentionally separate from the existing “NSE Data Test” workflow, so it does not replace or modify the working NSE scanner, RVOL, delivery, sector, or report-upload steps.

It runs on pushes to main, pull requests, and manual workflow_dispatch. It installs Python test dependencies, checks the required files, compiles the module and test, then runs:
  python -m pytest -q test_news_catalyst_matching.py

Expected: 5 focused tests pass. The workflow validates issuer matching only; it does not prove news availability, sector strength, a BUY signal, or the full V8 regression suite.

Required repository files already observed in the 2026-10-15 run:
  news_catalyst.py
  test_news_catalyst_matching.py
