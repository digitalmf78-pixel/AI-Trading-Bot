"""Regression tests: fundamental assessment errors must not leak candidates downstream."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def test_fundamental_pipeline_failure_fails_closed():
    source = (ROOT / "volume_gainer.py").read_text(encoding="utf-8")
    assert "Collection/assessment failed; no candidates advance" in source
    assert 'fundamental_audit["FundamentalAssessmentStatus"] = "WAIT_FOR_DATA"' in source
    assert 'fundamental_audit["FundamentalShortlistStatus"] = "WAIT_FOR_DATA"' in source
    assert "current = pd.DataFrame(columns=list(fundamental_audit.columns) if not fundamental_audit.empty else [])" in source
    assert "keep Delivery-A candidates and mark data unavailable" not in source
