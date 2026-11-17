"""Fetch and verify the ECMS U-Turn sample's official NSE UDiFF archives.

Research-only utility. Downloads only URLs listed in the checked-in NSE
session manifests. It never changes production data or sends Telegram output.
"""
from __future__ import annotations

import concurrent.futures
import csv
import hashlib
import io
import json
import os
import sys
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

from strategies.ecms.uturn_nse_ohlc import (
    build_nse_symbol_ohlc_window,
    extract_nse_eq_ohlc_row,
)

ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "research" / "ecms_uturn"
OUTPUT = Path(os.environ.get("UTURN_OUTPUT_DIR", "uturn_nse_audit_output"))
USER_AGENT = "Mozilla/5.0 (compatible; ECMS-U-Turn-Research/1.0; +https://github.com/digitalmf78-pixel/AI-Trading-Bot)"
TIMEOUT_SECONDS = 45
MAX_ATTEMPTS = 3


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def fetch_archive(url: str) -> tuple[bytes, str]:
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.get(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/zip,application/octet-stream,*/*",
                    "Referer": "https://www.nseindia.com/",
                },
                timeout=TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.content
            if not payload.startswith(b"PK"):
                raise ValueError(f"Response is not a ZIP archive (HTTP {response.status_code})")
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
                if len(csv_names) != 1:
                    raise ValueError(f"Expected one CSV in archive, found {len(csv_names)}")
                with archive.open(csv_names[0]) as stream:
                    table = pd.read_csv(stream, dtype=str)
            required = {"TradDt", "Sgmt", "FinInstrmTp", "TckrSymb", "SctySrs", "HghPric", "ClsPric", "ISIN"}
            if not required.issubset(table.columns):
                raise ValueError(f"UDiFF columns missing: {sorted(required - set(table.columns))}")
            return payload, table
        except Exception as exc:  # keep exact reason for the audit artifact
            last_error = exc
            if attempt < MAX_ATTEMPTS:
                time.sleep(attempt * 2)
    raise RuntimeError(f"Failed to fetch {url}: {last_error}")


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest = read_csv_rows(RESEARCH / "nse_ohlc_download_manifest.csv")
    latest_manifest = read_csv_rows(RESEARCH / "post_result_close_manifest.csv")
    if len(manifest) != 60 or len(latest_manifest) != 3:
        raise ValueError(f"Expected 60 peak-window rows and 3 latest-close rows; got {len(manifest)} and {len(latest_manifest)}")

    expected_by_symbol: dict[str, list[dict[str, str]]] = {}
    url_by_date: dict[str, str] = {}
    for row in manifest:
        symbol = row["Symbol"]
        date = row["Expected_NSE_Session"]
        if date >= row["Result_Announcement_Date"]:
            raise ValueError(f"{symbol}: peak session {date} is not strictly before announcement date")
        expected_by_symbol.setdefault(symbol, []).append(row)
        if date in url_by_date and url_by_date[date] != row["NSE_UDiFF_Bhavcopy_URL"]:
            raise ValueError(f"Conflicting NSE archive URLs for {date}")
        url_by_date[date] = row["NSE_UDiFF_Bhavcopy_URL"]

    for row in latest_manifest:
        date = row["Latest_Completed_Post_Result_Session_AsOf_2026_11_17"]
        url = row["NSE_UDiFF_Bhavcopy_URL"]
        if date in url_by_date and url_by_date[date] != url:
            raise ValueError(f"Conflicting NSE archive URLs for {date}")
        url_by_date[date] = url

    print(f"Downloading {len(url_by_date)} unique official NSE UDiFF archives for {len(expected_by_symbol)} symbols")
    downloaded: dict[str, tuple[bytes, pd.DataFrame]] = {}
    errors: list[str] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fetch_archive, url): date for date, url in url_by_date.items()}
        for future in concurrent.futures.as_completed(futures):
            date = futures[future]
            try:
                downloaded[date] = future.result()
                print(f"FETCH_OK {date} bytes={len(downloaded[date][0])}")
            except Exception as exc:
                errors.append(f"{date}: {exc}")
                print(f"FETCH_FAILED {date}: {exc}")

    verified_rows: list[dict] = []
    summaries: list[dict] = []
    for symbol, entries in sorted(expected_by_symbol.items()):
        sessions = [row["Expected_NSE_Session"] for row in entries]
        announcement_date = entries[0]["Result_Announcement_Date"]
        if len(sessions) != 20 or len(set(sessions)) != 20:
            summaries.append({"symbol": symbol, "status": "WAIT_FOR_DATA", "reason": "Manifest does not contain 20 unique sessions"})
            continue
        records = []
        for entry in entries:
            date = entry["Expected_NSE_Session"]
            if date not in downloaded:
                continue
            records.append({
                "session_date": date,
                "source_url": entry["NSE_UDiFF_Bhavcopy_URL"],
                "bhavcopy": downloaded[date][1],
            })
        if len(records) != 20:
            summaries.append({"symbol": symbol, "status": "WAIT_FOR_DATA", "reason": f"Only {len(records)}/20 archives downloaded"})
            continue
        window = build_nse_symbol_ohlc_window(
            records,
            symbol=symbol,
            expected_sessions=sessions,
            announcement_date=announcement_date,
            window_sessions=20,
        )
        if window["status"] != "READY":
            summaries.append({"symbol": symbol, "status": window["status"], "reason": window["reason"]})
            continue
        frame = window["ohlc"]
        for _, item in frame.iterrows():
            date = item["Date"]
            archive_bytes, _ = downloaded[date]
            verified_rows.append({
                "Symbol": symbol,
                "SessionDate": date,
                "High": item["High"],
                "Close": item["Close"],
                "ISIN": item["ISIN"],
                "NSEArchiveURL": item["SourceURL"],
                "ArchiveSHA256": hashlib.sha256(archive_bytes).hexdigest(),
                "Verification": "NSE_UDIFF_ROW_VERIFIED",
            })
        peak_idx = frame["High"].astype(float).idxmax()
        peak_row = frame.loc[peak_idx]
        summaries.append({
            "symbol": symbol,
            "status": "PEAK_WINDOW_VERIFIED_CA_REVIEW_PENDING",
            "announcement_date": announcement_date,
            "window_start": window["window_start"],
            "window_end": window["window_end"],
            "window_sessions": int(window["window_sessions"]),
            "isin": window["ISIN"],
            "pre_result_peak_high": float(peak_row["High"]),
            "pre_result_peak_date": str(peak_row["Date"]),
            "corporate_action_status": "REQUIRED_SEPARATE_REVIEW",
            "uturn_target_status": "WAIT_FOR_DATA",
        })

    for entry in latest_manifest:
        symbol = entry["Symbol"]
        date = entry["Latest_Completed_Post_Result_Session_AsOf_2026_11_17"]
        if date not in downloaded:
            errors.append(f"{symbol}: latest-close archive {date} unavailable")
            continue
        payload, table = downloaded[date]
        result = extract_nse_eq_ohlc_row(
            table,
            symbol=symbol,
            expected_session=date,
            source_url=entry["NSE_UDiFF_Bhavcopy_URL"],
        )
        summary = next((x for x in summaries if x["symbol"] == symbol), None)
        if result["status"] != "READY":
            errors.append(f"{symbol}: latest close not verified: {result['reason']}")
            if summary:
                summary["latest_close_status"] = result["status"]
            continue
        if summary:
            if summary.get("isin") != result["ISIN"]:
                summary["status"] = "UNVERIFIED_CORPORATE_ACTION_REVIEW"
                summary["latest_close_status"] = "ISIN_CHANGED"
            else:
                summary["latest_close_status"] = "VERIFIED"
            summary["latest_completed_session"] = date
            summary["latest_completed_close"] = result["Close"]
            summary["latest_close_isin"] = result["ISIN"]
        verified_rows.append({
            "Symbol": symbol,
            "SessionDate": date,
            "High": result["High"],
            "Close": result["Close"],
            "ISIN": result["ISIN"],
            "NSEArchiveURL": result["SourceURL"],
            "ArchiveSHA256": hashlib.sha256(payload).hexdigest(),
            "Verification": "NSE_UDIFF_ROW_VERIFIED_POST_RESULT_CLOSE",
        })

    pd.DataFrame(verified_rows).to_csv(OUTPUT / "verified_nse_ohlc_rows.csv", index=False)
    report = {
        "scope": "ECMS U-Turn research only",
        "source": "Official NSE UDiFF CM bhavcopy archives",
        "unique_archives_expected": len(url_by_date),
        "unique_archives_downloaded": len(downloaded),
        "verified_ohlc_rows": len(verified_rows),
        "download_errors": errors,
        "symbol_results": summaries,
        "corporate_action_review": "NOT PERFORMED BY THIS FETCHER; manual/official issuer-event reconciliation remains mandatory",
        "uturn_calculation": "NOT RUN; corporate-action comparability is not yet verified",
    }
    (OUTPUT / "audit_summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 1 if errors or len(downloaded) != len(url_by_date) or len(verified_rows) != 63 else 0


if __name__ == "__main__":
    sys.exit(main())
