from datetime import date

import pandas as pd

from strategies.ecms.information import (
    attach_valuation,
    collect_bulk_block_deals,
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
        ]})
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
