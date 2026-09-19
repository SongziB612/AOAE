"""Independent audit of the locally retained Treasury XML snapshot."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


ROOT = Path(__file__).parents[1]
RAW = ROOT / "data" / "raw" / "treasury" / "daily_treasury_yield_curve_2024.xml"
RESULT = ROOT / "research" / "data_admissions" / "0001-us-treasury-yield-curve" / "result.json"
FIELDS = (
    "BC_1MONTH", "BC_2MONTH", "BC_3MONTH", "BC_4MONTH", "BC_6MONTH",
    "BC_1YEAR", "BC_2YEAR", "BC_3YEAR", "BC_5YEAR", "BC_7YEAR",
    "BC_10YEAR", "BC_20YEAR", "BC_30YEAR",
)


def main() -> int:
    raw = RAW.read_bytes()
    recorded = json.loads(RESULT.read_text(encoding="utf-8"))
    root = ET.fromstring(raw)
    namespace = {"m": "http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"}
    rows = []
    for item in root.findall(".//m:properties", namespace):
        values = {child.tag.rsplit("}", 1)[-1]: child.text for child in item}
        observed = datetime.fromisoformat(values["NEW_DATE"]).date()
        rows.append((observed, {field: None if values.get(field) in {None, ""} else float(values[field]) for field in FIELDS}))

    dates = [row[0] for row in rows]
    evidence = {
        "row_count": len(rows),
        "first_date": dates[0].isoformat(),
        "last_date": dates[-1].isoformat(),
        "duplicate_date_count": len(dates) - len(set(dates)),
        "weekend_row_count": sum(value.weekday() >= 5 for value in dates),
        "out_of_period_count": sum(not datetime(2024, 1, 1).date() <= value <= datetime(2024, 12, 31).date() for value in dates),
        "field_quality": {},
    }
    for field in FIELDS:
        present = [row[field] for _, row in rows if row[field] is not None]
        missing_count = len(rows) - len(present)
        evidence["field_quality"][field] = {
            "missing_count": missing_count,
            "missing_fraction": round(missing_count / len(rows), 12),
            "minimum": min(present),
            "maximum": max(present),
        }

    failures = []
    if evidence != recorded["evidence"]:
        failures.append("recorded quality evidence differs from independent XML parsing")
    if hashlib.sha256(raw).hexdigest() != recorded["source"]["snapshot_sha256"]:
        failures.append("snapshot SHA-256 differs from the admitted record")
    if len(raw) != recorded["source"]["snapshot_bytes"]:
        failures.append("snapshot byte count differs from the admitted record")
    if dates != sorted(dates) or len(dates) != len(set(dates)):
        failures.append("dates are not strictly increasing and unique")

    if failures:
        print("independent_treasury_snapshot_audit=FAIL", file=sys.stderr)
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    print("independent_treasury_snapshot_audit=PASS")
    print(json.dumps({
        "rows": len(rows),
        "fields": len(FIELDS),
        "first_date": evidence["first_date"],
        "last_date": evidence["last_date"],
        "sha256": recorded["source"]["snapshot_sha256"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
