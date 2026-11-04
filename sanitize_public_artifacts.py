"""Remove account-derived position sizing from reports before public upload."""
from __future__ import annotations

import argparse
import csv
import os
import tempfile
from pathlib import Path


PRIVATE_RISK_COLUMNS = {
    "ProposedPositionQty",
    "RiskBudgetINR",
    "ProposedExposurePct",
}


def sanitize_report_csvs(root: str | Path = "outputs") -> dict[str, list[str]]:
    """Strip account-derived risk fields from every CSV under ``root``.

    Other report columns and values are preserved. Each affected CSV is replaced
    atomically so a failed write cannot leave a truncated artifact.
    """
    root = Path(root)
    if not root.exists():
        return {}
    sanitized: dict[str, list[str]] = {}
    for source in sorted(root.rglob("*.csv")):
        temporary_path = None
        try:
            with source.open("r", encoding="utf-8-sig", newline="") as stream:
                reader = csv.reader(stream)
                try:
                    header = next(reader)
                except StopIteration:
                    continue
                remove = [i for i, name in enumerate(header) if name in PRIVATE_RISK_COLUMNS]
                if not remove:
                    continue
                kept_header = [name for i, name in enumerate(header) if i not in remove]
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", newline="", dir=source.parent,
                    prefix=f".{source.name}.", suffix=".tmp", delete=False,
                ) as output:
                    temporary_path = Path(output.name)
                    writer = csv.writer(output, lineterminator="\n")
                    writer.writerow(kept_header)
                    for row in reader:
                        writer.writerow([value for i, value in enumerate(row) if i not in remove])
            # Close the source handle before replacement (required on Windows).
            os.replace(temporary_path, source)
        except Exception:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise
        sanitized[source.relative_to(root).as_posix()] = [header[i] for i in remove]
    return sanitized


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="outputs", help="report directory to sanitize")
    args = parser.parse_args()
    sanitized = sanitize_report_csvs(args.root)
    print(f"SANITIZED_REPORT_COUNT={len(sanitized)}")
    for path, columns in sanitized.items():
        print(f"SANITIZED={path};COLUMNS={','.join(columns)}")
    print("ACCOUNT_DERIVED_VALUES=REDACTED_FROM_PUBLIC_REPORTS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

