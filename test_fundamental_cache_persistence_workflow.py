"""Regression test: persistent fundamentals and official filing caches are restored between runs."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def test_workflow_cache_includes_fundamental_metrics_and_official_filings():
    workflow = (ROOT / ".github/workflows/nse-test-scheduled.yml").read_text(encoding="utf-8")
    assert "data/inputs/fundamental_metrics.csv" in workflow
    assert "outputs/v8_official_financial_results_filings.csv" in workflow
    assert "actions/cache@v5" in workflow
    assert "restore-keys:" in workflow


def test_provider_and_filing_cache_paths_match_workflow_cache_paths():
    provider = (ROOT / "fundamental_data_provider.py").read_text(encoding="utf-8")
    filings = (ROOT / "fundamental_official_filings.py").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/nse-test-scheduled.yml").read_text(encoding="utf-8")
    assert 'METRICS_PATH = INPUT_DIR / "fundamental_metrics.csv"' in provider
    assert 'FILINGS_CACHE = OUTPUT_DIR / "v8_official_financial_results_filings.csv"' in filings
    assert "data/inputs/fundamental_metrics.csv" in workflow
    assert "outputs/v8_official_financial_results_filings.csv" in workflow
