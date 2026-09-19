"""Independent byte-for-byte reconstruction of the canonical Treasury table."""

from __future__ import annotations

import csv
from datetime import datetime
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


ROOT = Path(__file__).parents[1]
RAW = ROOT / "data" / "raw" / "treasury" / "daily_treasury_yield_curve_2024.xml"
DERIVED = ROOT / "data" / "processed" / "treasury" / "yield_curve_2024_canonical.csv"
RESULT = ROOT / "research" / "derived_datasets" / "0001-treasury-curve-canonical" / "result.json"
SOURCE_FIELDS = {
    "yield_1m_pct": "BC_1MONTH", "yield_2m_pct": "BC_2MONTH",
    "yield_3m_pct": "BC_3MONTH", "yield_4m_pct": "BC_4MONTH",
    "yield_6m_pct": "BC_6MONTH", "yield_1y_pct": "BC_1YEAR",
    "yield_2y_pct": "BC_2YEAR", "yield_3y_pct": "BC_3YEAR",
    "yield_5y_pct": "BC_5YEAR", "yield_7y_pct": "BC_7YEAR",
    "yield_10y_pct": "BC_10YEAR", "yield_20y_pct": "BC_20YEAR",
    "yield_30y_pct": "BC_30YEAR",
}
COLUMNS = (
    "observation_date", *SOURCE_FIELDS,
    "spread_10y_2y_bps", "spread_10y_3m_bps", "spread_30y_10y_bps",
    "change_2y_bps", "change_10y_bps",
)


def main() -> int:
    raw = RAW.read_bytes()
    root = ET.fromstring(raw)
    namespace = {"m": "http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"}
    source_rows = []
    for item in root.findall(".//m:properties", namespace):
        values = {child.tag.rsplit("}", 1)[-1]: child.text for child in item}
        observed = datetime.fromisoformat(values["NEW_DATE"]).date()
        source_rows.append((observed, {column: Decimal(values[field]) for column, field in SOURCE_FIELDS.items()}))
    source_rows.sort(key=lambda item: item[0])

    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    previous = None
    spreads_10_2 = []
    spreads_10_3m = []
    spreads_30_10 = []
    changes_2y = []
    changes_10y = []
    for observed, yields in source_rows:
        s10_2 = int((yields["yield_10y_pct"] - yields["yield_2y_pct"]) * 100)
        s10_3m = int((yields["yield_10y_pct"] - yields["yield_3m_pct"]) * 100)
        s30_10 = int((yields["yield_30y_pct"] - yields["yield_10y_pct"]) * 100)
        change_2y = "" if previous is None else int((yields["yield_2y_pct"] - previous["yield_2y_pct"]) * 100)
        change_10y = "" if previous is None else int((yields["yield_10y_pct"] - previous["yield_10y_pct"]) * 100)
        row = {"observation_date": observed.isoformat()}
        row.update({column: f"{value:.2f}" for column, value in yields.items()})
        row.update({
            "spread_10y_2y_bps": s10_2, "spread_10y_3m_bps": s10_3m,
            "spread_30y_10y_bps": s30_10, "change_2y_bps": change_2y,
            "change_10y_bps": change_10y,
        })
        writer.writerow(row)
        spreads_10_2.append(s10_2)
        spreads_10_3m.append(s10_3m)
        spreads_30_10.append(s30_10)
        if previous is not None:
            changes_2y.append(int(change_2y))
            changes_10y.append(int(change_10y))
        previous = yields

    rebuilt = output.getvalue().encode("utf-8")
    retained = DERIVED.read_bytes()
    recorded = json.loads(RESULT.read_text(encoding="utf-8"))
    evidence = {
        "row_count": len(source_rows), "column_count": len(COLUMNS),
        "first_date": source_rows[0][0].isoformat(), "last_date": source_rows[-1][0].isoformat(),
        "inverted_10y_2y_rows": sum(value < 0 for value in spreads_10_2),
        "inverted_10y_3m_rows": sum(value < 0 for value in spreads_10_3m),
        "spread_10y_2y_bps_minimum": min(spreads_10_2), "spread_10y_2y_bps_maximum": max(spreads_10_2),
        "spread_10y_3m_bps_minimum": min(spreads_10_3m), "spread_10y_3m_bps_maximum": max(spreads_10_3m),
        "spread_30y_10y_bps_minimum": min(spreads_30_10), "spread_30y_10y_bps_maximum": max(spreads_30_10),
        "maximum_absolute_2y_daily_change_bps": max(abs(value) for value in changes_2y),
        "maximum_absolute_10y_daily_change_bps": max(abs(value) for value in changes_10y),
    }
    failures = []
    if rebuilt != retained:
        failures.append("retained canonical CSV differs byte-for-byte from independent reconstruction")
    if hashlib.sha256(rebuilt).hexdigest() != recorded["output"]["sha256"]:
        failures.append("derived SHA-256 differs from record")
    if evidence != recorded["evidence"]:
        failures.append("derived descriptive evidence differs from record")
    if failures:
        print("independent_treasury_curve_audit=FAIL", file=sys.stderr)
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    print("independent_treasury_curve_audit=PASS")
    print(json.dumps({"rows": len(source_rows), "columns": len(COLUMNS), "sha256": recorded["output"]["sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
