import pandas as pd

from fundamental_data_provider import _aligned_annual_metrics, collect_missing_fundamentals
from fundamental_shortlist import build_fundamental_shortlist, DEFAULT_THRESHOLDS

D0, D1 = pd.Timestamp("2026-03-31"), pd.Timestamp("2025-03-31")


def _df(rows, dates=(D0, D1)):
    return pd.DataFrame(rows, columns=list(dates)).rename_axis(None)




class AlignedTicker:
    sector_name = "Industrials"

    def __init__(self, symbol, cash_date=D0):
        self.info = {"sector": self.sector_name, "revenueGrowth": 9.99}  # snapshot must be ignored
        cols = [D0, D1]
        self.financials = pd.DataFrame({D0: [1200, 150, 300, 50], D1: [1000, 100, 250, 50]},
                                       index=["Total Revenue", "Net Income", "EBIT", "Interest Expense"])
        self.balance_sheet = pd.DataFrame({D0: [3000, 1000, 1200, 600], D1: [2800, 900, 1000, 600]},
                                          index=["Total Assets", "Current Liabilities", "Stockholders Equity", "Total Debt"])
        self.cashflow = pd.DataFrame({cash_date: [200, -80], D1: [150, -60]},
                                     index=["Operating Cash Flow", "Capital Expenditure"])


class MisalignedTicker(AlignedTicker):
    def __init__(self, symbol):
        super().__init__(symbol, cash_date=pd.Timestamp("2025-09-30"))


def test_aligned_metrics_use_one_period_and_ignore_info_snapshot():
    out = _aligned_annual_metrics(AlignedTicker("AAA"))
    assert out["ok"] and out["period_end"] == "2026-03-31"
    v = out["values"]
    assert round(v["RevenueGrowthPct"], 2) == 20.0
    assert round(v["ProfitGrowthPct"], 2) == 50.0
    assert round(v["ROEPercent"], 2) == round(150 / 1100 * 100, 2)   # average equity
    assert round(v["ROCEPercent"], 2) == round(300 / 2000 * 100, 2)
    assert round(v["DebtToEquity"], 2) == 0.5
    assert round(v["InterestCoverage"], 2) == 6.0
    assert v["OperatingCashFlowINR"] == 200 and v["FreeCashFlowINR"] == 120


def test_period_mismatch_is_not_aligned():
    out = _aligned_annual_metrics(MisalignedTicker("AAA"))
    assert not out["ok"] and "STATEMENT_PERIODS_DIFFER" in out["reason"]


def test_provider_marks_alignment_verified_and_replaces_stale_unverified(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    kw = dict(enabled=True, pause_seconds=0, asof_date="2026-10-22", filings_fetcher=lambda _c: pd.DataFrame())
    r = collect_missing_fundamentals(pd.DataFrame({"TckrSymb": ["AAA"]}), ticker_factory=MisalignedTicker, **kw)
    assert r.set_index("TckrSymb").loc["AAA", "MetricPeriodAlignmentStatus"] == "UNVERIFIED"
    # Remove metrics so the record is provider-owned again, keep the stale UNVERIFIED flag.
    path = tmp_path / "data/inputs/fundamental_metrics.csv"
    df = pd.read_csv(path)
    for c in ["RevenueGrowthPct", "ProfitGrowthPct", "ROEPercent", "ROCEPercent", "DebtToEquity",
              "InterestCoverage", "OperatingCashFlowINR", "FreeCashFlowINR", "EarningsQualityStatus", "ValuationStatus"]:
        df[c] = pd.NA
    df.to_csv(path, index=False)
    r = collect_missing_fundamentals(pd.DataFrame({"TckrSymb": ["AAA"]}), ticker_factory=AlignedTicker, **kw)
    row = r.set_index("TckrSymb").loc["AAA"]
    assert row["MetricPeriodAlignmentStatus"] == "VERIFIED"
    assert str(row["FinancialPeriodEnd"])[:10] == "2026-03-31"
    assert row["ProviderSector"] == "Industrials"


def _verified_row(**over):
    row = {"TckrSymb": "AAA", "PublicationDateStatus": "VERIFIED", "MetricPeriodAlignmentStatus": "VERIFIED",
           "FinancialPeriodEnd": "2026-03-31", "PublicationDate": "2026-05-20", "ProviderSector": "Industrials",
           "RevenueGrowthPct": 20, "ProfitGrowthPct": 50, "ROEPercent": 14, "ROCEPercent": 15,
           "DebtToEquity": 0.5, "InterestCoverage": 6, "OperatingCashFlowINR": 200, "FreeCashFlowINR": -5}
    row.update(over)
    return row


def status(**over):
    out = build_fundamental_shortlist(pd.DataFrame([_verified_row(**over)]), "2026-10-22",
                                      thresholds=dict(DEFAULT_THRESHOLDS), write=False)
    return out.iloc[0]["FundamentalShortlistStatus"], out.iloc[0]["FundamentalShortlistReason"]


def test_pass_even_with_negative_fcf_by_default():
    assert status()[0] == "PASS"


def test_fail_when_threshold_missed():
    s, why = status(DebtToEquity=2.5)
    assert s == "FAIL" and "DebtToEquity" in why


def test_unverified_or_missing_data_is_wait_not_pass():
    assert status(MetricPeriodAlignmentStatus="UNVERIFIED")[0] == "WAIT_FOR_DATA"
    assert status(PublicationDateStatus="UNVERIFIED")[0] == "WAIT_FOR_DATA"
    assert status(ROCEPercent=None)[0] == "WAIT_FOR_DATA"
    assert status(PublicationDate="2026-11-01")[0] == "WAIT_FOR_DATA"
    assert status(FinancialPeriodEnd="2024-12-31")[0] == "WAIT_FOR_DATA"  # too old


def test_financial_sector_needs_special_rules_and_rows_are_kept():
    s, why = status(ProviderSector="Financial Services")
    assert s == "WAIT_FOR_DATA" and "SPECIAL_RULES" in why
    df = pd.DataFrame([_verified_row(), _verified_row(TckrSymb="BBB", DebtToEquity=3)])
    out = build_fundamental_shortlist(df, "2026-10-22", write=False)
    assert len(out) == 2


def test_duplicate_fundamental_records_cannot_pass_and_assessment_status_stays_synced():
    row = _verified_row(FundamentalReason="DUPLICATE_FUNDAMENTAL_RECORDS")
    out = build_fundamental_shortlist(pd.DataFrame([row]), "2026-10-22", write=False)
    assert out.iloc[0]["FundamentalShortlistStatus"] == "WAIT_FOR_DATA"
    assert "DUPLICATE_FUNDAMENTAL_RECORDS" in out.iloc[0]["FundamentalShortlistReason"]
    assert out.iloc[0]["FundamentalAssessmentStatus"] == out.iloc[0]["FundamentalShortlistStatus"]
    assert out.iloc[0]["FundamentalAssessmentReason"] == out.iloc[0]["FundamentalShortlistReason"]


def test_assessment_status_syncs_for_pass_fail_and_wait():
    rows = [
        _verified_row(TckrSymb="PASS"),
        _verified_row(TckrSymb="FAIL", ROEPercent=1),
        _verified_row(TckrSymb="WAIT", PublicationDateStatus="UNVERIFIED"),
    ]
    out = build_fundamental_shortlist(pd.DataFrame(rows), "2026-10-22", write=False)
    assert out["FundamentalAssessmentStatus"].tolist() == out["FundamentalShortlistStatus"].tolist()
    assert out["FundamentalAssessmentReason"].tolist() == out["FundamentalShortlistReason"].tolist()
