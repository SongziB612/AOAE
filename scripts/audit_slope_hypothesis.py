"""Implementation-independent recalculation of locked HYP-0002."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
from statistics import median
import sys
import xml.etree.ElementTree as ET


ROOT = Path(__file__).parents[1]
RAW = ROOT / "data" / "raw" / "treasury" / "daily_treasury_yield_curve_2023.xml"
SPEC = ROOT / "research" / "hypotheses" / "0002-treasury-slope-inversion" / "spec.json"
RESULT = ROOT / "research" / "hypotheses" / "0002-treasury-slope-inversion" / "result.json"
PREREGISTRATION_COMMIT = "42b6dfc"


def main() -> int:
    raw = RAW.read_bytes()
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    recorded = json.loads(RESULT.read_text(encoding="utf-8"))
    root = ET.fromstring(raw)
    namespace = {"m": "http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"}
    rows: list[tuple[date, Decimal, Decimal]] = []
    missing = 0
    for item in root.findall(".//m:properties", namespace):
        values = {child.tag.rsplit("}", 1)[-1]: child.text for child in item}
        if not values.get("NEW_DATE"):
            continue
        if not values.get("BC_2YEAR") or not values.get("BC_10YEAR"):
            missing += 1
            continue
        rows.append((
            datetime.fromisoformat(values["NEW_DATE"]).date(),
            Decimal(values["BC_2YEAR"]),
            Decimal(values["BC_10YEAR"]),
        ))

    dates = [row[0] for row in rows]
    spreads = [float((two_year - ten_year) * 100) for _, two_year, ten_year in rows]
    inversion_count = sum(spread > 0 for spread in spreads)
    inversion_rate = round(inversion_count / len(spreads), 12)
    evidence = {
        "inversion_count": inversion_count,
        "inversion_rate": inversion_rate,
        "mean_two_year_minus_ten_year_bps": round(math.fsum(spreads) / len(spreads), 12),
        "median_two_year_minus_ten_year_bps": round(median(spreads), 12),
        "minimum_two_year_minus_ten_year_bps": round(min(spreads), 12),
        "maximum_two_year_minus_ten_year_bps": round(max(spreads), 12),
    }
    start = date.fromisoformat(spec["data"]["period_start"])
    end = date.fromisoformat(spec["data"]["period_end"])
    minimum_rows = spec["decision_rule"]["minimum_observations"]
    maximum_rows = spec["data"]["maximum_rows"]
    threshold = spec["decision_rule"]["minimum_inversion_rate"]

    failures = []
    if evidence != recorded["evidence"]:
        failures.append("recorded evidence differs from independent recalculation")
    if hashlib.sha256(raw).hexdigest() != recorded["data"]["snapshot_sha256"]:
        failures.append("holdout snapshot hash differs from record")
    if len(raw) != recorded["data"]["snapshot_bytes"] or len(rows) != recorded["data"]["rows"]:
        failures.append("holdout byte or row count differs from record")
    if missing != 0 or not minimum_rows <= len(rows) <= maximum_rows:
        failures.append("required-field completeness or row bounds failed")
    if dates != sorted(set(dates)) or not all(start <= observed <= end for observed in dates):
        failures.append("date order, uniqueness, or holdout bounds failed")
    if recorded["preregistration_commit"] != PREREGISTRATION_COMMIT:
        failures.append("unexpected preregistration commit")
    expected_pass = inversion_rate >= threshold
    if expected_pass != (recorded["result"]["status"] == "PASS"):
        failures.append("recorded decision differs from locked threshold")
    if recorded["capital_authorized"] or recorded["strategy_mining_authorized"]:
        failures.append("record improperly authorizes strategy mining or capital")

    if failures:
        print("independent_slope_hypothesis_audit=FAIL", file=sys.stderr)
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    print("independent_slope_hypothesis_audit=PASS")
    print(json.dumps({"rows": len(rows), **evidence}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
