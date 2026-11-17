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
import threading
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.ecms.uturn_nse_ohlc import (
    build_nse_symbol_ohlc_window,
    extract_nse_eq_ohlc_row,
)

RESEARCH = ROOT / "research" / "ecms_uturn"
OUTPUT = Path(os.environ.get("UTURN_OUTPUT_DIR", "uturn_nse_audit_output"))
USER_AGENT = "Mozilla/5.0 (compatible; ECMS-U-Turn-Research/1.0; +https://github.com/digitalmf78-pixel/AI-Trading-Bot)"
CONNECT_TIMEOUT_SECONDS = 15
READ_TIMEOUT_SECONDS = 35
MAX_ATTEMPTS = 2
_thread_local = threading.local()


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _nse_session() -> requests.Session:
    """Create one warmed NSE session per worker thread.

    NSE archive hosts can stall requests that arrive without a fresh website
    session. Prime cookies on the public NSE site before requesting archives.
    """
    session = getattr(_thread_local, "session", None)
    if session is not None:
        return session

    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "application/zip,application/octet-stream,*/*",
        "Accept-Language": "en-IN,en;q=0.9",
        "Connection": "keep-alive",
        "Referer": "https://www.nseindia.com/all-reports",
    })
    # Establish the public-site session first; no login or credentials used.
    warm = session.get(
        "https://www.nseindia.com/",
        headers={"Accept": "text/html,application/xhtml+xml"},
        timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
    )
    warm.raise_for_status()
    _thread_local.session = session
    return session


def fetch_archive(url: str) -> tuple[bytes, pd.DataFrame]:
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            session = _nse_session()
            with session.get(
                url,
                stream=True,
                timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
            ) as response:
                response.raise_for_status()
                chunks = []
                for chunk in response.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        chunks.append(chunk)
                payload = b"".join(chunks)

            if not payload.startswith(b"PK"):
                preview = payload[:160].decode("utf-8", errors="replace")
                raise ValueError(
                    f"Response is not a ZIP archive; bytes={len(payload)}, preview={preview!r}"
                )
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
                if len(csv_names) != 1:
                    raise ValueError(f"Expected one CSV in archive, found {len(csv_names)}")
                with archive.open(csv_names[0]) as stream:
                    table = pd.read_csv(stream, dtype=str)

            required = {
                "TradDt", "Sgmt", "FinInstrmTp", "TckrSymb",
                "SctySrs", "HghPric", "ClsPric", "ISIN",
            }
            if not required.issubset(table.columns):
                raise ValueError(f"UDiFF columns missing: {sorted(required - set(table.columns))}")
            return payload, table
        except Exception as exc:
            last_error = exc
            # A stale/bad cookie session is discarded before the one retry.
            if hasattr(_thread_local, "session"):
                del _thread_local.session
            if attempt < MAX_ATTEMPTS:
                time.sleep(3 * attempt)
    raise RuntimeError(f"Failed to fetch {url}: {last_error}")


def main() -> int:
    """Download every unique manifest archive and emit auditable evidence.

    A failed/incomplete sample still writes a summary and exits non-zero so
    GitHub Actions cannot report a green data-audit step for an empty output.
    """
    output = ROOT / OUTPUT if not OUTPUT.is_absolute() else OUTPUT
    output.mkdir(parents=True, exist_ok=True)

    peak_manifest = read_csv_rows(RESEARCH / "nse_ohlc_download_manifest.csv")
    close_manifest = read_csv_rows(RESEARCH / "post_result_close_manifest.csv")
    if not peak_manifest or not close_manifest:
        raise RuntimeError("One or more NSE manifests are empty")

    # The manifest is the allow-list: no URLs are generated or inferred here.
    url_to_expected = {}
    for row in peak_manifest:
        url_to_expected.setdefault(row["NSE_UDiFF_Bhavcopy_URL"], set()).add(
            row["Expected_NSE_Session"]
        )
    for row in close_manifest:
        url_to_expected.setdefault(row["NSE_UDiFF_Bhavcopy_URL"], set()).add(
            row["Latest_Completed_Post_Result_Session_AsOf_2026_11_17"]
        )

    print(f"Manifest peak rows: {len(peak_manifest)}")
    print(f"Manifest post-result close rows: {len(close_manifest)}")
    print(f"Unique official NSE archives to fetch: {len(url_to_expected)}", flush=True)

    downloaded = {}
    archive_audit = []
    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(fetch_archive, url): url for url in url_to_expected}
        for future in concurrent.futures.as_completed(futures):
            url = futures[future]
            try:
                payload, table = future.result()
                downloaded[url] = table
                archive_audit.append({
                    "SourceURL": url,
                    "Status": "DOWNLOADED_SCHEMA_VALID",
                    "Bytes": len(payload),
                    "SHA256": hashlib.sha256(payload).hexdigest(),
                    "Rows": len(table),
                    "ExpectedDates": ";".join(sorted(url_to_expected[url])),
                })
                print(
                    f"DOWNLOADED {len(downloaded)}/{len(url_to_expected)} "
                    f"{url.rsplit('/', 1)[-1]} rows={len(table)}",
                    flush=True,
                )
            except Exception as exc:
                failures.append({"SourceURL": url, "Error": str(exc)})
                archive_audit.append({
                    "SourceURL": url,
                    "Status": "DOWNLOAD_FAILED",
                    "Bytes": 0,
                    "SHA256": "",
                    "Rows": 0,
                    "ExpectedDates": ";".join(sorted(url_to_expected[url])),
                })
                print(f"DOWNLOAD_FAILED {url}: {exc}", flush=True)

    verified_rows = []
    symbol_summaries = []
    for symbol in sorted({row["Symbol"] for row in peak_manifest}):
        symbol_rows = [row for row in peak_manifest if row["Symbol"] == symbol]
        sessions = [row["Expected_NSE_Session"] for row in symbol_rows]
        announcement_date = symbol_rows[0]["Result_Announcement_Date"]
        records = []
        for row in symbol_rows:
            url = row["NSE_UDiFF_Bhavcopy_URL"]
            if url in downloaded:
                records.append({
                    "session_date": row["Expected_NSE_Session"],
                    "source_url": url,
                    "bhavcopy": downloaded[url],
                })
        result = build_nse_symbol_ohlc_window(
            records,
            symbol=symbol,
            expected_sessions=sessions,
            announcement_date=announcement_date,
            window_sessions=20,
        )
        if result["status"] == "READY":
            verified_rows.extend(result["ohlc"].to_dict(orient="records"))
        symbol_summaries.append({
            "Symbol": symbol,
            "AnnouncementDate": announcement_date,
            "ExpectedSessions": len(sessions),
            "DownloadedSessions": len(records),
            "VerifiedSessions": (
                result["window_sessions"] if result["status"] == "READY" else 0
            ),
            "Status": result["status"],
            "Reason": result["reason"],
            "WindowStart": result.get("window_start", ""),
            "WindowEnd": result.get("window_end", ""),
            "ISIN": result.get("ISIN", ""),
        })
        print(
            f"SYMBOL {symbol}: {result['status']} "
            f"verified_sessions={result.get('window_sessions', 0)} "
            f"reason={result['reason']}",
            flush=True,
        )

    post_result_rows = []
    for row in close_manifest:
        symbol = row["Symbol"]
        session = row["Latest_Completed_Post_Result_Session_AsOf_2026_11_17"]
        url = row["NSE_UDiFF_Bhavcopy_URL"]
        if url not in downloaded:
            post_result_rows.append({
                "Symbol": symbol, "Date": session, "Status": "WAIT_FOR_DATA",
                "Reason": "Official NSE archive download failed", "SourceURL": url,
            })
            continue
        extracted = extract_nse_eq_ohlc_row(
            downloaded[url],
            symbol=symbol,
            expected_session=session,
            source_url=url,
        )
        post_result_rows.append({**extracted, "SourceURL": url})
        print(
            f"POST_RESULT_CLOSE {symbol}: {extracted['status']} "
            f"{session} {extracted.get('Close', '')} {extracted.get('reason', '')}",
            flush=True,
        )

    pd.DataFrame(archive_audit).to_csv(output / "archive_audit.csv", index=False)
    pd.DataFrame(verified_rows).to_csv(output / "verified_nse_ohlc_rows.csv", index=False)
    pd.DataFrame(symbol_summaries).to_csv(output / "symbol_window_summary.csv", index=False)
    pd.DataFrame(post_result_rows).to_csv(output / "post_result_close_rows.csv", index=False)

    summary = {
        "research_only": True,
        "source": "official NSE nsearchives UDiFF CM bhavcopy",
        "manifest_peak_rows": len(peak_manifest),
        "manifest_post_result_close_rows": len(close_manifest),
        "unique_archives": len(url_to_expected),
        "downloaded_archives": len(downloaded),
        "failed_archives": len(failures),
        "verified_peak_ohlc_rows": len(verified_rows),
        "symbols": symbol_summaries,
        "post_result_close_rows": post_result_rows,
        "corporate_action_review": "PENDING",
        "eps_source_revalidation": "PENDING",
        "uturn_target_calculation_performed": False,
        "failures": failures,
    }
    (output / "audit_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        "AUDIT_SUMMARY "
        + json.dumps({
            "unique_archives": len(url_to_expected),
            "downloaded_archives": len(downloaded),
            "failed_archives": len(failures),
            "verified_peak_ohlc_rows": len(verified_rows),
            "symbols_ready": sum(item["Status"] == "READY" for item in symbol_summaries),
        }),
        flush=True,
    )

    # Do not let an empty/incomplete data run masquerade as a successful audit.
    all_symbols_ready = all(item["Status"] == "READY" for item in symbol_summaries)
    all_closes_ready = all(item.get("status") == "READY" for item in post_result_rows)
    if failures or not all_symbols_ready or not all_closes_ready:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
