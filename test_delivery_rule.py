def passes(values):
    return len(values) == 5 and all(v is not None and v >= 60.0 for v in values)

def test_all_five_at_least_60_pass():
    assert passes([61, 65, 70, 60.0, 99])

def test_exactly_60_passes():
    assert passes([61, 65, 70, 60.0, 99])

def test_one_below_60_rejects():
    assert not passes([61, 65, 59.99, 70, 99])

def test_missing_session_waits_or_fails_closed():
    assert not passes([61, 65, 70, 99])

def test_average_does_not_matter():
    assert not passes([99, 99, 99, 99, 59.99])
