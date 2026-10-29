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


def test_workflow_caches_dated_fundamental_history_snapshots():
    workflow = (ROOT / ".github/workflows/nse-test-scheduled.yml").read_text(encoding="utf-8")
    provider = (ROOT / "fundamental_data_provider.py").read_text(encoding="utf-8")
    assert "data/cache/fundamental_history/" in workflow
    assert "save_fundamental_history_snapshot" in provider


def test_fundamental_history_snapshot_is_dated_and_preserves_csv(tmp_path):
    import pandas as pd
    from fundamental_data_provider import save_fundamental_history_snapshot

    metrics = tmp_path / "fundamental_metrics.csv"
    pd.DataFrame([{"TckrSymb": "AAA", "PublicationDateStatus": "VERIFIED"}]).to_csv(metrics, index=False)
    history = tmp_path / "history"
    snapshot = save_fundamental_history_snapshot(metrics, "2026-10-28", history)
    assert snapshot is not None
    assert snapshot.name == "fundamental_metrics_2026-10-28.csv"
    saved = pd.read_csv(snapshot)
    assert saved.loc[0, "TckrSymb"] == "AAA"
    assert saved.loc[0, "PublicationDateStatus"] == "VERIFIED"


def test_fundamental_assessment_is_written_and_pass_gate_is_applied():
    source = (ROOT / "volume_gainer.py").read_text(encoding="utf-8")
    assert 'fundamental_audit["FundamentalAssessmentStatus"] = fundamental_audit["FundamentalShortlistStatus"].astype(str)' in source
    assert 'eq("PASS")' in source
    assert "Fundamental PASS advancing={len(current)}" in source
    assert 'v8_fundamental_report.csv' in source
