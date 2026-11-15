import pandas as pd

from tools.ecms_gemini_research import DEFAULT_MODEL, extract_json, row_payload


def test_extract_json_accepts_json_fenced_response():
    result = extract_json(chr(96) * 3 + 'json\\n{"symbol":"ABC","research_classification":"GOOD"}\\n' + chr(96) * 3)
    assert result["symbol"] == "ABC"
    assert result["research_classification"] == "GOOD"


def test_extract_json_rejects_non_object_response():
    try:
        extract_json("No structured result")
    except ValueError as exc:
        assert "JSON object" in str(exc)
    else:
        raise AssertionError("Expected invalid JSON response to be rejected")


def test_row_payload_excludes_internal_metric_source_json():
    row = pd.Series({
        "TckrSymb": "ABC",
        "RevenueGrowthPct": 18.5,
        "MetricSourcesJSON": '{"RevenueGrowthPct":"yfinance"}',
        "SourceURL": "https://example.com/report",
    })
    result = row_payload(row)
    assert result["TckrSymb"] == "ABC"
    assert result["RevenueGrowthPct"] == 18.5
    assert "MetricSourcesJSON" not in result


def test_default_gemini_model_uses_current_supported_flash_model():
    assert DEFAULT_MODEL == "gemini-3.8-flash"
