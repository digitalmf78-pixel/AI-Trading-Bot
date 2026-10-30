from valuation_parsing import extract_stock_pe, classify_relative_pe, parse_positive_number


def test_extract_stock_pe_from_normalized_screener_text():
    assert extract_stock_pe("Market Cap 10,000 Cr Stock P/E 18.50 Book Value") == 18.5


def test_extract_stock_pe_handles_whitespace_and_case():
    assert extract_stock_pe("stock   p / e   24.2") == 24.2


def test_extract_stock_pe_returns_none_when_missing_or_nonpositive():
    assert extract_stock_pe("Stock P/E NA") is None
    assert parse_positive_number("-4.2") is None


def test_relative_pe_classification_uses_peer_median():
    status, median, ratio = classify_relative_pe(8, [10, 12, 11, 9, 13])
    assert status == "RELATIVELY_UNDERVALUED"
    assert median == 11
    assert round(ratio, 4) == round(8 / 11, 4)


def test_relative_pe_requires_three_valid_peers():
    assert classify_relative_pe(10, [12, None, "N/A"])[0] == "DATA_INSUFFICIENT"


def test_nonpositive_own_pe_is_not_misclassified_as_cheap():
    assert classify_relative_pe(-5, [10, 11, 12])[0] == "DATA_INSUFFICIENT"
