from fundamental_data_provider import _free_source_observation_row


def test_primary_secondary_observation_keeps_its_period_url_and_currency():
    result = {
        "metric_sources": {"ROEPercent": "Moneycontrol"},
        "metric_periods": {"ROEPercent": "Mar 2026"},
        "metric_urls": {"ROEPercent": "https://www.moneycontrol.com/ratio"},
        "metric_currencies": {"ROEPercent": ""},
    }

    row = _free_source_observation_row("ROEPercent", 16.71, result)

    assert row == {
        "source": "Moneycontrol",
        "value": 16.71,
        "period": "Mar 2026",
        "source_url": "https://www.moneycontrol.com/ratio",
        "currency": "",
    }


def test_secondary_observation_without_period_stays_explicitly_blank():
    row = _free_source_observation_row("DebtToEquity", 0.78, {
        "metric_sources": {"DebtToEquity": "Moneycontrol"},
        "metric_periods": {},
        "metric_urls": {},
        "metric_currencies": {},
    })

    assert row["period"] == ""
    assert row["source"] == "Moneycontrol"
    assert row["value"] == 0.78
