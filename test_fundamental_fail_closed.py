"""Regression tests: fundamental assessment errors must not leak candidates downstream."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def test_fundamental_pipeline_failure_marks_wait_and_stops_downstream_candidates():
    source = (ROOT / "volume_gainer.py").read_text(encoding="utf-8")
    assert "Collection/assessment/verification failed" in source
    assert 'fundamental_audit["FundamentalAssessmentStatus"] = "WAIT_FOR_DATA"' in source
    assert 'fundamental_audit["FundamentalShortlistStatus"] = "WAIT_FOR_DATA"' in source
    assert 'fallback_pass_mask = fundamental_audit.get(' in source
    assert 'current = fundamental_audit.loc[fallback_pass_mask].copy()' in source
    assert "Only explicit PASS rows can proceed" in source
    assert "fallback_a_mask" not in source

