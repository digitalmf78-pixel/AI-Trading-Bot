"""Regression guard for the live-scan entry point and consolidation helper.

A helper defined *after* ``if __name__ == "__main__": main()`` is invisible when
the scanner runs as a script, even though imports and unit tests pass. That is
how the 2026-11-10 scheduled scans failed after ~8 minutes with NameError.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

import volume_gainer

SOURCE = Path(__file__).resolve().parent / "volume_gainer.py"


def test_entrypoint_has_no_top_level_definitions_after_it():
    lines = SOURCE.read_text(encoding="utf-8").splitlines()
    entry_index = next(
        index for index, line in enumerate(lines)
        if line.strip().startswith('if __name__ == "__main__":')
    )
    offenders = [
        (number, line)
        for number, line in enumerate(lines[entry_index + 1:], start=entry_index + 2)
        if line.startswith(("def ", "class "))
    ]
    assert not offenders, (
        "Top-level definitions after the entry point will raise NameError on a "
        f"live scan: {offenders}"
    )


def test_consolidation_helper_is_defined_before_entrypoint():
    source = SOURCE.read_text(encoding="utf-8")
    assert source.index("def calculate_consolidation_score") < source.index(
        'if __name__ == "__main__":'
    )


def test_consolidation_score_runs_on_synthetic_history():
    result = pd.DataFrame([{"TckrSymb": "ABC"}])
    history = pd.DataFrame({
        "TckrSymb": ["ABC"] * 20,
        "Date": pd.date_range("2026-01-01", periods=20),
        "OpnPric": [100.0] * 20,
        "HghPric": [100.2] * 20,
        "LwPric": [99.8] * 20,
        "ClsPric": [100.0 + (index % 2) * 0.1 for index in range(20)],
        "TtlTradgVol": [1_000] * 20,
    })
    out = volume_gainer.calculate_consolidation_score(result, [history])
    assert out.loc[0, "ConsolidationStatus"] == "TIGHT_CONSOLIDATION"
    assert out.loc[0, "ConsolidationScore"] == 90.0


def test_consolidation_score_handles_empty_result():
    empty = pd.DataFrame(columns=["TckrSymb"])
    assert volume_gainer.calculate_consolidation_score(empty, []).empty



def test_forward_outcomes_are_warning_only_and_never_gate_scanner_rows():
    source = SOURCE.read_text(encoding="utf-8")
    start = source.index("    signal_rows_written = append_signal_log")
    end = source.index("    # Later-stage watchlists are independent copies;", start)
    block = source[start:end]
    assert "try:" in block
    assert "update_signal_outcomes(" in block
    assert "except Exception as outcome_exc:" in block
    assert "[SIGNAL OUTCOMES] WARNING" in block
    assert "result =" not in block
    assert "return" not in block


def test_unbounded_shadow_jsonl_writer_is_not_wired_into_live_scanner():
    source = SOURCE.read_text(encoding="utf-8")
    assert "build_mainboard_signal_shadow" not in source
    assert "append_immutable_jsonl" not in source
