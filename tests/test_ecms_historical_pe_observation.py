from strategies.ecms.historical_pe_observation import calculate_historical_pe_reference


def rows(count=20):
    return [
        {
            "pe": float(10 + i),
            "price_date": f"2025-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}",
            "eps_period": f"TTM ending {i}",
            "eps_basis": "TTM_DILUTED",
            "source": "fixture:synthetic",
        }
        for i in range(count)
    ]


def calculate(data=None, **overrides):
    args = {
        "current_eps": 10,
        "current_eps_basis": "TTM_DILUTED",
        "current_eps_period": "TTM ending 2026-09-30",
        "current_eps_source": "fixture:synthetic",
        "as_of_date": "2026-11-16",
        "lower_percentile": 20,
        "min_observations": 20,
    }
    args.update(overrides)
    return calculate_historical_pe_reference(rows() if data is None else data, **args)


def test_calculates_interpolated_lower_band_and_reference_price():
    result = calculate()
    assert result["status"] == "HISTORICAL_VALUATION_REFERENCE"
    assert result["historical_pe_lower_band"] == 13.8
    assert result["historical_pe_median"] == 19.5
    assert result["historical_pe_upper_band_p75"] == 24.25
    assert result["valuation_reference_price"] == 138.0
    assert result["technical_status"] == "NOT_ASSESSED"


def test_rejects_non_positive_or_non_finite_current_eps():
    for eps in (0, -1, "nan", None):
        assert calculate(current_eps=eps)["reason"] == "CURRENT_EPS_NOT_POSITIVE_FINITE"


def test_rejects_non_positive_historical_pe():
    data = rows()
    data[0]["pe"] = 0
    assert calculate(data)["reason"] == "HISTORICAL_PE_NOT_POSITIVE_FINITE"


def test_rejects_mixed_eps_basis():
    data = rows()
    data[0]["eps_basis"] = "BASIC_EPS"
    assert calculate(data)["reason"] == "EPS_BASIS_MISMATCH"


def test_rejects_insufficient_history():
    assert calculate(rows(19))["reason"] == "INSUFFICIENT_HISTORICAL_OBSERVATIONS"


def test_rejects_missing_source_provenance():
    data = rows()
    data[0]["source"] = ""
    assert calculate(data)["reason"] == "HISTORICAL_PROVENANCE_MISSING"


def test_rejects_duplicate_dates():
    data = rows()
    data[1]["price_date"] = data[0]["price_date"]
    assert calculate(data)["reason"] == "DUPLICATE_HISTORICAL_PRICE_DATE"


def test_rejects_future_dated_observation():
    data = rows()
    data[-1]["price_date"] = "2026-11-17"
    assert calculate(data)["reason"] == "FUTURE_HISTORICAL_OBSERVATION"


def test_rejects_missing_current_eps_provenance():
    assert calculate(current_eps_source="")["reason"] == "CURRENT_EPS_PROVENANCE_MISSING"


def test_rejects_invalid_percentile():
    assert calculate(lower_percentile=50)["reason"] == "LOWER_PERCENTILE_OUT_OF_RANGE"
    assert calculate(lower_percentile="bad")["reason"] == "LOWER_PERCENTILE_OUT_OF_RANGE"
