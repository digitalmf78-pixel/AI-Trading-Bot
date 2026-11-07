def avg_category(values):
    return len(values) == 5 and all(v is not None for v in values) and sum(values) / 5 >= 60.0

def daily_category(values):
    return len(values) == 5 and all(v is not None and v >= 60.0 for v in values)

def test_average_category_passes_when_average_is_at_least_60():
    assert avg_category([55, 65, 58, 70, 62])

def test_average_category_exactly_60_passes():
    assert avg_category([50, 60, 60, 65, 65])

def test_daily_category_requires_each_of_five_at_least_60():
    assert daily_category([61, 65, 70, 60.0, 99])
    assert not daily_category([61, 65, 59.99, 70, 99])

def test_both_categories_pass_when_each_day_is_at_least_60():
    values = [61, 65, 70, 60.0, 99]
    assert avg_category(values) and daily_category(values)

def test_missing_session_waits_or_fails_closed():
    assert not avg_category([61, 65, 70, 99])
    assert not daily_category([61, 65, 70, 99])


def avg_category_30d(values):
    return len(values) >= 5 and all(v is not None for v in values) and sum(values) / len(values) >= 60.0

def daily_category_30d(values):
    return len(values) >= 5 and all(v is not None and v >= 60.0 for v in values)

def test_30d_categories_accept_more_than_five_valid_sessions():
    values = [60.0, 61.0, 62.0, 63.0, 64.0, 65.0, 66.0]
    assert avg_category_30d(values)
    assert daily_category_30d(values)

def test_30d_category_a_uses_average_of_all_valid_sessions():
    values = [50.0, 62.0, 62.0, 62.0, 62.0, 62.0]
    assert avg_category_30d(values)
    assert not daily_category_30d(values)

def test_30d_categories_wait_when_fewer_than_five_valid_sessions():
    values = [65.0, 66.0, 67.0, 68.0]
    assert not avg_category_30d(values)
    assert not daily_category_30d(values)
