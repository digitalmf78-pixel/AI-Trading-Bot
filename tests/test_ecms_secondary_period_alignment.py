from strategies.ecms.volume_gainers import (
    _normalize_ecms_secondary_period,
    _secondary_period_alignment_status,
)


def test_moneycontrol_month_period_matches_yahoo_fiscal_year_end():
    assert _secondary_period_alignment_status(
        "ROEPercent", "Mar 2026", "2026-03-31"
    ) == ("2026-03-31", "MATCHED_YAHOO_PERIOD")


def test_growth_fiscal_year_pair_normalizes_to_current_year_end():
    assert _secondary_period_alignment_status(
        "RevenueGrowthPct", "FY2025->FY2026", "2026-03-31"
    ) == ("2026-03-31", "MATCHED_YAHOO_PERIOD")


def test_tickertape_zero_period_is_quarantined_not_inferred():
    assert _normalize_ecms_secondary_period("ROEPercent", "0") == ""
    assert _secondary_period_alignment_status(
        "ROEPercent", "0", "2026-03-31"
    ) == ("", "SECONDARY_PERIOD_INVALID")


def test_old_secondary_period_is_flagged_as_mismatch():
    assert _secondary_period_alignment_status(
        "ROEPercent", "Jun 2022", "2026-03-31"
    ) == ("2022-06-30", "MISMATCHED_YAHOO_PERIOD")


def test_growth_pair_must_be_consecutive_and_growth_metric():
    assert _normalize_ecms_secondary_period("RevenueGrowthPct", "FY2024->FY2026") == ""
    assert _normalize_ecms_secondary_period("ROEPercent", "FY2025->FY2026") == ""
