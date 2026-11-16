from datetime import date

import pandas as pd

from strategies.ecms.information import (
    attach_valuation,
    collect_bulk_block_deals,
    collect_corporate_actions,
    collect_upcoming_events,
)


class FakeResponse:
    def __init__(self, payload=None, text=""):
        self.payload = payload
        self.text = text

    def raise_for_status(self):
        return None

    def json(self):
        if self.payload is None:
            raise ValueError("not json")
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.headers = {}
        self.responses = list(responses)

    def get(self, url, **kwargs):
        if "companies-listing" in url or "report-detail" in url:
            return FakeResponse(payload={})
        return self.responses.pop(0)


def test_event_calendar_separates_upcoming_events_and_next_result():
    client = FakeSession([
        FakeResponse(payload={"data": [
            {"symbol": "AAA", "date": "20-Nov-2026", "purpose": "Financial Results",
             "details": "Q2 FY27 results board meeting"},
            {"symbol": "AAA", "date": "25-Nov-2026", "purpose": "Investor Meet",
             "details": "Investor conference"},
            {"symbol": "BBB", "date": "21-Nov-2026", "purpose": "Dividend"},
        ]}),
        FakeResponse(payload=[]),
    ])
    events, audit = collect_upcoming_events(["AAA", "BBB"], date(2026, 11, 15), session=client)

    assert len(events) == 3
    aaa = audit.set_index("TckrSymb").loc["AAA"]
    assert aaa["NextResultDate"] == "2026-11-20"
    assert "Investor Meet" in aaa["UpcomingEvents"]
    assert audit.set_index("TckrSymb").loc["BBB", "NextResultDate"] == "NOT ANNOUNCED"


def test_bulk_and_block_deals_are_parsed_as_disclosed_sides():
    csv_bulk = (
        "Date,Symbol,Security Name,Client Name,Buy / Sell,Quantity Traded,"
        "Trade Price / Wght. Avg. Price,Remarks\n"
        "14-Nov-2026,AAA,AAA LIMITED,Fund Alpha,BUY,100000,125.50,Bulk Deal\n"
        "14-Nov-2026,AAA,AAA LIMITED,Fund Beta,SELL,100000,125.50,Bulk Deal\n"
    )
    csv_block = (
        "Date,Symbol,Security Name,Client Name,Buy / Sell,Quantity Traded,"
        "Trade Price / Wght. Avg. Price,Remarks\n"
        "13-Nov-2026,AAA,AAA LIMITED,Investor Gamma,BUY,50000,124.00,Block Deal\n"
    )
    client = FakeSession([FakeResponse(text=csv_bulk), FakeResponse(text=csv_block)])
    deals, audit = collect_bulk_block_deals(["AAA", "BBB"], date(2026, 11, 15), session=client)

    assert len(deals) == 3
    aaa = audit.set_index("TckrSymb").loc["AAA"]
    assert aaa["BulkDealCount"] == 2
    assert aaa["BlockDealCount"] == 1
    assert aaa["BulkDealCountLast5Days"] == 2
    assert aaa["BlockDealCountLast5Days"] == 1
    assert "BULK 2026-11-14" in aaa["BulkBlockSummaryLast5Days"]
    assert aaa["BulkBuyers"] == "Fund Alpha"
    assert aaa["BulkSellers"] == "Fund Beta"
    assert audit.set_index("TckrSymb").loc["BBB", "BulkBlockDealStatus"] == "NO_DISCLOSED_DEALS_IN_LOOKBACK"


def test_valuation_label_requires_provenance_and_is_informational():
    frame = pd.DataFrame([
        {"ValuationSource": "Yahoo Finance", "ValuationAsOfDate": "2026-11-14",
         "ProviderSector": "Industrials", "TrailingPE": 18, "PEG": 0.8},
        {"ValuationSource": "", "ValuationAsOfDate": "", "TrailingPE": 10, "PEG": 0.5},
        {"ValuationSource": "Yahoo Finance", "ValuationAsOfDate": "2026-11-14",
         "ProviderSector": "Banking", "PriceToBook": 3.5},
    ])
    result = attach_valuation(frame)
    assert result["ValuationLabel"].tolist() == ["CHEAP", "NOT AVAILABLE", "EXPENSIVE"]
    assert result["ValuationBasis"].iloc[0] == "TRAILING_PE_AND_PEG_INDICATIVE_BANDS"


def test_as_date_recognizes_iso_exchange_date_without_dayfirst_ambiguity():
    from strategies.ecms.information import _as_date
    assert _as_date("2026-11-15") == date(2026, 11, 15)
    assert _as_date("15-Nov-2026") == date(2026, 11, 15)



def test_news_uses_five_trading_sessions_and_reuses_only_complete_exact_window_cache(tmp_path, monkeypatch):
    from strategies.ecms import eod

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(eod, "UNIVERSE_DIR", tmp_path / "missing-universe")
    monkeypatch.setattr(eod, "is_trading_session", lambda day: day.weekday() < 5)
    calls = {"official": 0, "secondary": 0}
    requested = []

    def official(symbol, start, end):
        calls["official"] += 1
        requested.append((start, end))
        return ([{"TckrSymb": symbol, "PublishedDate": end.isoformat(),
                  "Headline": "Official filing", "Source": "NSE",
                  "SourceType": "OFFICIAL", "URL": "https://nseindia.com"}], "AVAILABLE")

    def secondary(symbol, company, start, end):
        calls["secondary"] += 1
        return ([], "AVAILABLE")

    candidates = pd.DataFrame([{"TckrSymb": "AAA"}])
    first, audit = eod.collect_catalysts(
        candidates, date(2026, 11, 13),
        official_fetcher=official, secondary_fetcher=secondary,
    )
    second, second_audit = eod.collect_catalysts(
        candidates, date(2026, 11, 13),
        official_fetcher=official, secondary_fetcher=secondary,
    )

    assert requested == [(date(2026, 11, 9), date(2026, 11, 13))]
    assert calls == {"official": 1, "secondary": 1}
    assert len(first) == len(second) == 1
    assert audit.iloc[0]["NewsWindowStart"] == "2026-11-09"
    assert second_audit.iloc[0]["CatalystStatus"] == "CATALYST_FOUND"



def test_corporate_actions_are_fetched_once_for_all_symbols_and_cached(tmp_path, monkeypatch):
    from strategies.ecms import information

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(information, "is_trading_session", lambda day: day.weekday() < 5)
    client = FakeSession([
        FakeResponse(payload=[
            {"symbol": "AAA", "exDate": "20-Nov-2026", "subject": "Dividend - Rs 5",
             "recDate": "21-Nov-2026", "bcStartDate": "-", "bcEndDate": "-",
             "payDate": "05-Dec-2026"},
            {"symbol": "AAA", "exDate": "10-Nov-2026", "subject": "Bonus 1:1",
             "recDate": "11-Nov-2026"},
            {"symbol": "OUTSIDE", "exDate": "20-Nov-2026", "subject": "Dividend"},
        ])
    ])

    actions, audit = collect_corporate_actions(
        ["AAA", "BBB"], date(2026, 11, 13), session=client
    )

    assert len(actions) == 2
    assert set(actions["TckrSymb"]) == {"AAA"}
    assert set(audit["TckrSymb"]) == {"AAA", "BBB"}
    rows = audit.set_index("TckrSymb")
    assert rows.loc["AAA", "CorporateActionsStatus"] == "DATA_FOUND"
    assert rows.loc["AAA", "CorporateActionCount"] == 2
    assert rows.loc["BBB", "CorporateActionsStatus"] == "NO_DATA_FOUND"
    assert rows.loc["AAA", "CorporateActionWindowStart"] == "2026-11-09"
    assert rows.loc["AAA", "CorporateActionWindowEnd"] == "2027-02-11"

    # The exact date-window response is stored once; a later call reuses it.
    actions_again, audit_again = collect_corporate_actions(
        ["AAA", "BBB"], date(2026, 11, 13)
    )
    assert len(actions_again) == 2
    assert audit_again.set_index("TckrSymb").loc["AAA", "CorporateActionsStatus"] == "DATA_FOUND"


def test_board_meetings_feed_parses_nse_bm_fields_and_result_date():
    client = FakeSession([
        FakeResponse(payload=[]),
        FakeResponse(payload=[{
            "bm_symbol": "AAA",
            "bm_date": "25-Nov-2026",
            "bm_purpose": "Financial Results",
            "bm_desc": "To consider and approve quarterly unaudited financial results",
        }]),
    ])
    events, audit = collect_upcoming_events(["AAA", "BBB"], date(2026, 11, 16), session=client)

    assert len(events) == 1
    assert events.iloc[0]["Source"] == "NSE Board Meetings"
    row = audit.set_index("TckrSymb").loc["AAA"]
    assert row["NextResultDate"] == "2026-11-25"
    assert row["UpcomingEventsSourceCoverageStatus"] == "COMPLETE"


def test_bulk_deals_support_official_bd_prefixed_fields():
    client = FakeSession([
        FakeResponse(payload=[{
            "BD_DT_DATE": "01-DEC-2025",
            "BD_SYMBOL": "AAA",
            "BD_CLIENT_NAME": "Fund Alpha",
            "BD_BUY_SELL": "BUY",
            "BD_QTY_TRD": 108709,
            "BD_TP_WATP": 826.15,
            "BD_REMARKS": "Disclosed bulk deal",
        }]),
        FakeResponse(payload=[]),
    ])
    deals, audit = collect_bulk_block_deals(["AAA"], date(2025, 12, 1), session=client)

    assert len(deals) == 1
    assert deals.iloc[0]["TckrSymb"] == "AAA"
    assert deals.iloc[0]["ClientName"] == "Fund Alpha"
    assert deals.iloc[0]["Quantity"] == 108709
    assert deals.iloc[0]["PriceINR"] == 826.15
    assert deals.iloc[0]["Side"] == "BUY"
