"""Independent recalculation of the locked HYP-0001 holdout test."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


ROOT = Path(__file__).parents[1]
RAW = ROOT / "data" / "raw" / "treasury" / "daily_treasury_yield_curve_2025.xml"
RESULT = ROOT / "research" / "hypotheses" / "0001-treasury-yield-comovement" / "result.json"


def correlation(left: list[float], right: list[float]) -> float:
    left_mean = math.fsum(left) / len(left)
    right_mean = math.fsum(right) / len(right)
    covariance = math.fsum((x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True))
    left_ss = math.fsum((x - left_mean) ** 2 for x in left)
    right_ss = math.fsum((y - right_mean) ** 2 for y in right)
    return covariance / math.sqrt(left_ss * right_ss)


def main() -> int:
    raw = RAW.read_bytes()
    root = ET.fromstring(raw)
    namespace = {"m": "http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"}
    rows = []
    missing = 0
    for item in root.findall(".//m:properties", namespace):
        values = {child.tag.rsplit("}", 1)[-1]: child.text for child in item}
        if not values.get("NEW_DATE"):
            continue
        if not values.get("BC_2YEAR") or not values.get("BC_10YEAR"):
            missing += 1
            continue
        rows.append((datetime.fromisoformat(values["NEW_DATE"]).date(), Decimal(values["BC_2YEAR"]), Decimal(values["BC_10YEAR"])))

    changes_2y = [float((current[1] - previous[1]) * 100) for previous, current in zip(rows, rows[1:])]
    changes_10y = [float((current[2] - previous[2]) * 100) for previous, current in zip(rows, rows[1:])]
    evidence = {
        "pearson_correlation": round(correlation(changes_2y, changes_10y), 12),
        "same_direction_rate": round(sum((x > 0) == (y > 0) for x, y in zip(changes_2y, changes_10y, strict=True)) / len(changes_2y), 12),
        "mean_2y_change_bps": round(math.fsum(changes_2y) / len(changes_2y), 12),
        "mean_10y_change_bps": round(math.fsum(changes_10y) / len(changes_10y), 12),
    }
    recorded = json.loads(RESULT.read_text(encoding="utf-8"))
    failures = []
    if evidence != recorded["evidence"]:
        failures.append("recorded metrics differ from independent recalculation")
    if hashlib.sha256(raw).hexdigest() != recorded["data"]["snapshot_sha256"]:
        failures.append("holdout snapshot hash differs from record")
    if len(raw) != recorded["data"]["snapshot_bytes"] or len(rows) != recorded["data"]["rows"]:
        failures.append("holdout byte or row count differs from record")
    if missing != 0 or len(changes_2y) != recorded["method"]["paired_changes"]:
        failures.append("required-field or paired-change count differs")
    if recorded["preregistration_commit"] != "d7d1bca":
        failures.append("unexpected preregistration commit")
    if failures:
        print("independent_real_hypothesis_audit=FAIL", file=sys.stderr)
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    print("independent_real_hypothesis_audit=PASS")
    print(json.dumps({"rows": len(rows), "paired_changes": len(changes_2y), **evidence}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
