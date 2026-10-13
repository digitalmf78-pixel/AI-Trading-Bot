"""Standalone smoke test for NSE CM-UDiFF EOD Bhavcopy ingestion.

This test is intentionally separate from the NIFTY 500 index API diagnostic.
It validates the same Bhavcopy download/normalization path used by the scanner.
"""
import sys

from volume_gainer import get_latest_eod, prepare_equity_data


def main() -> int:
    try:
        eod_date, raw = get_latest_eod()
        if raw is None or raw.empty:
            print("Bhavcopy test FAILED: empty EOD response")
            return 1

        clean = prepare_equity_data(raw)
        if clean.empty:
            print("Bhavcopy test FAILED: no listed-equity rows after normalization")
            return 1

        required = {
            "TckrSymb", "OpnPric", "HghPric", "LwPric",
            "ClsPric", "PrvsClsgPric", "TtlTradgVol",
        }
        missing = sorted(required - set(clean.columns))
        if missing:
            print(f"Bhavcopy test FAILED: missing columns: {missing}")
            return 1

        print(f"Bhavcopy test PASSED: EOD date={eod_date}; equity rows={len(clean)}")
        print("Sample symbols:", ", ".join(clean["TckrSymb"].head(10).astype(str)))
        return 0
    except Exception as exc:
        print(f"Bhavcopy test FAILED: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
