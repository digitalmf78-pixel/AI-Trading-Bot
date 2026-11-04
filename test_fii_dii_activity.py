import pandas as pd

from fii_dii_activity import (
    DATA_SCOPE,
    attach_market_context,
    parse_activity_rows,
    write_market_activity,
)


def _rows(day="03-Nov-2026"):
    return [
        {"category": "DII", "date": day, "buyValue": "20", "sellValue": "25", "netValue": "-5"},
        {"category": "FII/FPI", "date": day, "buyValue": "40", "sellValue": "30", "netValue": "10"},
    ]


def test_exact_date_market_wide_flow_reconciles_and_is_not_stock_level():
    result = parse_activity_rows(_rows(), "2026-11-03")
    assert result["DataStatus"] == "OFFICIAL_PROVISIONAL_EXACT_DATE"
    assert result["FiiFpiNetINRCrore"] == 10
    assert result["DiiNetINRCrore"] == -5
    assert result["NetValueCheck"] == "PASS"
    assert result["DataScope"] == DATA_SCOPE
    assert result["MarketFlowInterpretation"] == "FII_FPI_BUYING_DII_SELLING"


def test_date_mismatch_preserves_values_but_never_marks_them_current():
    result = parse_activity_rows(_rows(), "2026-11-04")
    assert result["DataStatus"] == "WAIT_FOR_DATA_DATE_MISMATCH"
    assert result["DataDate"] == "2026-11-03"
    assert result["FiiFpiNetINRCrore"] == 10


def test_bad_net_value_or_missing_category_fails_closed():
    bad = _rows()
    bad[0]["netValue"] = "4"
    assert parse_activity_rows(bad, "2026-11-03")["DataStatus"] == "WAIT_FOR_DATA_NET_VALUE_MISMATCH"
    assert parse_activity_rows(_rows()[:1], "2026-11-03")["DataStatus"] == "WAIT_FOR_DATA_INCOMPLETE_CATEGORIES"


def test_report_is_written_even_when_unavailable_and_attachment_is_context_only(tmp_path):
    record = parse_activity_rows(_rows(), "2026-11-03")
    path = tmp_path / "outputs" / "market.csv"
    saved = write_market_activity("2026-11-03", record, path)
    report = pd.read_csv(path)
    assert len(report) == 1 and report.loc[0, "DataScope"] == DATA_SCOPE
    frame = attach_market_context(pd.DataFrame({"TckrSymb": ["AAA"]}), saved)
    assert frame.loc[0, "FiiDiiFiiFpiNetINRCrore"] == 10
    assert frame.loc[0, "FiiDiiScope"] == DATA_SCOPE
    assert "CandidateRank" not in frame.columns

