from scripts.research_mainboard_fundamental_coverage import compare


def test_coverage_sets_are_exact_and_deduplicated():
    main, cached, missing, outside = compare(
        {"AAA", "BBB", "CCC", "AAA"},
        {"CCC"},
        {"AAA", "ZZZ"},
    )
    assert main == {"AAA", "BBB"}
    assert cached == {"AAA"}
    assert missing == {"BBB"}
    assert outside == {"ZZZ"}


def test_empty_official_universe_fails_closed():
    import pytest
    with pytest.raises(ValueError):
        compare(set(), {"SME"}, {"AAA"})
