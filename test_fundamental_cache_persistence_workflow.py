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


def test_fundamental_assessment_uses_metric_verification_before_selection():
    source = (ROOT / "volume_gainer.py").read_text(encoding="utf-8")
    liquidity = source.index("STEP 6: EXISTING LIQUIDITY FILTER")
    fundamentals = source.index("STEP 7: FUNDAMENTALS FOR ALL RVOL > 1.5 DELIVERY A/B CANDIDATES")
    technical = source.index("Calculate technical features for every stock that passed Delivery and Liquidity")
    assert liquidity < fundamentals < technical
    assert "fundamental_collection_candidates = current.loc[" in source
    assert "collect_missing_fundamentals(\n                    fundamental_collection_candidates" in source
    assert "run_fundamental_metric_audit(symbols=evidence_symbols)" in source
    assert "Fundamental score/status is enrichment only and never removes a candidate" in source
    assert "fundamental_pass_mask" not in source
    assert 'v8_fundamental_report.csv' in source


def test_workflow_commits_fundamental_cache_and_history_to_repository():
    workflow = (ROOT / ".github/workflows/nse-test-scheduled.yml").read_text(encoding="utf-8")
    assert "permissions:\n  contents: write" in workflow
    assert "Persist fundamental cache and dated history in repository" in workflow
    assert 'git add -f data/inputs/fundamental_metrics.csv' in workflow
    # Accept the safer inventory-and-stage implementation used by the workflow.
    assert "mapfile -d '' HISTORY_FILES" in workflow
    assert "find data/cache/fundamental_history -maxdepth 1 -type f -name '*.csv' -print0 | sort -z" in workflow
    assert 'git add -f -- "$f"' in workflow
    assert "HISTORY_CSV_COUNT=${#HISTORY_FILES[@]}" in workflow
    assert "HISTORY_TRACKING_STATUS=TRACKED:$f" in workflow
    assert "git diff --cached --name-status" in workflow
    assert 'git push origin "HEAD:${GITHUB_REF_NAME}"' in workflow
    assert 'git fetch origin "${GITHUB_REF_NAME}"' in workflow
    assert 'git -c rebase.autoStash=true rebase "origin/${GITHUB_REF_NAME}"' in workflow
    assert "if: always() && steps.nse_scan.outcome == 'success'" in workflow
    assert "concurrency:" in workflow
    assert "cancel-in-progress: ${{ github.event_name == 'push' }}" in workflow
    assert "steps.nse_scan.outcome == 'success'" in workflow


def test_every_scan_sends_telegram_notifications():
    workflow = (ROOT / ".github/workflows/nse-test-scheduled.yml").read_text(encoding="utf-8")
    assert 'SEND_TELEGRAM: "true"' in workflow
    assert "Notify Telegram when any NSE workflow step fails" in workflow
    assert "if: ${{ failure() }}" in workflow
    assert "steps.nse_scan.outcome == 'failure'" not in workflow
