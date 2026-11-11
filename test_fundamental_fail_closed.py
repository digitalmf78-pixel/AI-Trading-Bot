"""Regression tests: fundamental enrichment errors must not remove liquidity candidates."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def test_fundamental_pipeline_failure_keeps_liquidity_candidates():
    source = (ROOT / "volume_gainer.py").read_text(encoding="utf-8")
    assert "Collection/score error; keeping all Liquidity-qualified candidates" in source
    assert 'fundamental_audit["FundamentalStatus"] = "MISSING_DATA"' in source
    assert 'fundamental_audit["Fundamental65PlusStatus"] = "WAIT_FOR_DATA"' in source
    assert "current = liquidity_pass_candidates.copy()" in source
    assert "Fundamental score/status is enrichment only and never removes a candidate" in source
    assert "current = fundamental_audit.loc[fallback_pass_mask].copy()" not in source
