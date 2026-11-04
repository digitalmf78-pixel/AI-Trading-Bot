import csv

from sanitize_public_artifacts import sanitize_report_csvs


def test_sanitizer_removes_account_derived_fields_and_preserves_other_report_data(tmp_path):
    outputs = tmp_path / "outputs"
    nested = outputs / "nested"
    nested.mkdir(parents=True)
    report = nested / "eod.csv"
    report.write_text(
        "TckrSymb,ProposedPositionQty,RiskBudgetINR,ProposedExposurePct,RiskControlStatus\n"
        "AAA,12,1000,24.25,PASS\n",
        encoding="utf-8",
    )
    unaffected = outputs / "safe.csv"
    unaffected.write_text("TckrSymb,Status\nAAA,WAIT_FOR_DATA\n", encoding="utf-8")

    changed = sanitize_report_csvs(outputs)

    assert changed == {
        "nested/eod.csv": [
            "ProposedPositionQty", "RiskBudgetINR", "ProposedExposurePct",
        ],
    }
    with report.open("r", encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert rows == [{"TckrSymb": "AAA", "RiskControlStatus": "PASS"}]
    assert unaffected.read_text(encoding="utf-8") == "TckrSymb,Status\nAAA,WAIT_FOR_DATA\n"


def test_sanitizer_is_safe_when_report_directory_is_missing(tmp_path):
    assert sanitize_report_csvs(tmp_path / "absent") == {}

