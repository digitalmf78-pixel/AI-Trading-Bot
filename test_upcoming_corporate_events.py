from __future__ import annotations

import os
import xml.etree.ElementTree as ET

import pandas as pd

import news_catalyst as news


def _item(title: str, description: str = "", published: str = "2026-10-19T12:00:00+05:30", url: str = "https://nsearchives.nseindia.com/example.pdf"):
    item = ET.Element("item")
    for key, value in {
        "title": title,
        "description": description,
        "pubDate": published,
        "link": url,
        "symbol": "ABC",
    }.items():
        node = ET.SubElement(item, key)
        node.text = value
    return item


def test_explicit_future_board_meeting_date_is_recorded_as_official_event():
    item = _item(
        "Board Meeting Intimation",
        "The Board meeting will be held on 28-Oct-2026 to consider quarterly financial results.",
    )
    rows = news._upcoming_event_rows_for_item("ABC", item, "2026-10-20", "EOD")
    assert len(rows) == 1
    assert rows[0]["EventDate"] == "2026-10-28"
    assert rows[0]["EventType"] == "RESULTS"
    assert rows[0]["Status"] == "OFFICIAL_DATE_CONFIRMED"
    assert rows[0]["SourceType"] == "PRIMARY_OFFICIAL"
    assert rows[0]["URL"].endswith("example.pdf")


def test_future_result_date_in_long_month_format_is_parsed():
    item = _item(
        "Financial Results",
        "Board meeting scheduled for October 29, 2026.",
    )
    rows = news._upcoming_event_rows_for_item("ABC", item, "2026-10-20", "EOD")
    assert rows
    assert rows[0]["EventDate"] == "2026-10-29"


def test_past_event_date_is_not_labelled_upcoming():
    item = _item(
        "Outcome of Board Meeting",
        "Board meeting was held on 18-Oct-2026 to consider financial results.",
    )
    rows = news._upcoming_event_rows_for_item("ABC", item, "2026-10-20", "EOD")
    assert len(rows) == 1
    assert rows[0]["EventDate"] == ""
    assert rows[0]["Status"] == "DATE_NOT_FOUND_OR_NO_FUTURE_DATE"


def test_irrelevant_announcement_is_not_added_as_upcoming_event():
    item = _item("Shareholding Pattern", "Shareholding pattern for the quarter ended.")
    assert news._upcoming_event_rows_for_item("ABC", item, "2026-10-20", "EOD") == []


def test_event_report_has_one_status_row_per_shortlisted_symbol_and_no_other_symbols(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rows = [{
        "EODDate": "2026-10-20",
        "TckrSymb": "ABC",
        "EventType": "RESULTS",
        "EventDate": "2026-10-28",
        "AnnouncementDate": "2026-10-19",
        "Headline": "Board meeting to consider results",
        "Source": "NSE India",
        "SourceType": "PRIMARY_OFFICIAL",
        "URL": "https://nseindia.com/announcement",
        "Status": "OFFICIAL_DATE_CONFIRMED",
        "LookbackDays": "90",
    }]
    news._write_upcoming_events_report({"ABC", "XYZ"}, rows, {"ABC": True, "XYZ": False}, "2026-10-20")
    out = pd.read_csv("outputs/v8_upcoming_corporate_events.csv").fillna("")
    assert set(out["TckrSymb"]) == {"ABC", "XYZ"}
    assert out.loc[out["TckrSymb"] == "ABC", "Status"].iloc[0] == "OFFICIAL_DATE_CONFIRMED"
    assert out.loc[out["TckrSymb"] == "XYZ", "Status"].iloc[0] == "WAIT_FOR_DATA"
    assert len(out) == 2
