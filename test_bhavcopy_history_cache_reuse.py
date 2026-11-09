from datetime import date
import pandas as pd

import volume_gainer


def _bhavcopy_row(symbol: str, volume: int = 1000, biz_date: str = "2026-11-04") -> pd.DataFrame:
    return pd.DataFrame([{
        "BizDt": biz_date,
        "TckrSymb": symbol,
        "OpnPric": 100,
        "HghPric": 105,
        "LwPric": 99,
        "ClsPric": 103,
        "PrvsClsgPric": 101,
        "TtlTradgVol": volume,
        "SctySrs": "EQ",
    }])


def test_collect_historical_days_reuses_cache_without_download(tmp_path, monkeypatch):
    monkeypatch.setattr(volume_gainer, "DATA_CACHE_DIR", str(tmp_path))
    _bhavcopy_row("AAA").to_csv(tmp_path / "bhavcopy_20261104.csv", index=False)
    _bhavcopy_row("BBB", biz_date="2026-11-05").to_csv(tmp_path / "bhavcopy_20261105.csv", index=False)
    # The current EOD date must not be included as a prior session.
    _bhavcopy_row("CURRENT", biz_date="2026-11-06").to_csv(tmp_path / "bhavcopy_20261106.csv", index=False)

    def unexpected_download(_):
        raise AssertionError("NSE download must not run when the cache has enough sessions")

    monkeypatch.setattr(volume_gainer, "download_bhavcopy", unexpected_download)

    history = volume_gainer.collect_historical_days(date(2026, 11, 6), days=2)

    assert len(history) == 2
    assert [frame["Date"].iloc[0].date() for frame in history] == [
        date(2026, 11, 4),
        date(2026, 11, 5),
    ]
    assert set(history[-1]["TckrSymb"]) == {"BBB"}


def test_collect_historical_days_downloads_only_when_cache_is_incomplete(tmp_path, monkeypatch):
    monkeypatch.setattr(volume_gainer, "DATA_CACHE_DIR", str(tmp_path))
    _bhavcopy_row("CACHED", biz_date="2026-11-05").to_csv(tmp_path / "bhavcopy_20261105.csv", index=False)
    downloaded_dates = []

    def download_once(day):
        downloaded_dates.append(day.date())
        if day.date() == date(2026, 11, 4):
            return _bhavcopy_row("FETCHED", biz_date="2026-11-04")
        return None

    monkeypatch.setattr(volume_gainer, "download_bhavcopy", download_once)

    history = volume_gainer.collect_historical_days(date(2026, 11, 6), days=2)

    assert len(history) == 2
    assert [frame["Date"].iloc[0].date() for frame in history] == [
        date(2026, 11, 4),
        date(2026, 11, 5),
    ]
    assert downloaded_dates == [date(2026, 11, 4)]
