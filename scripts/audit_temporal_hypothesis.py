"""Implementation-independent recalculation of locked HYP-0003."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


ROOT = Path(__file__).parents[1]
RAW = ROOT / "data" / "raw" / "treasury" / "daily_treasury_yield_curve_2022.xml"
SPEC = ROOT / "research" / "hypotheses" / "0003-treasury-slope-change-reversal" / "spec.json"
RESULT = ROOT / "research" / "hypotheses" / "0003-treasury-slope-change-reversal" / "result.json"
PREREGISTRATION_COMMIT = "b618128"


def correlation(left: list[float], right: list[float]) -> float:
    left_mean = math.fsum(left) / len(left)
    right_mean = math.fsum(right) / len(right)
    covariance = math.fsum((x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True))
    left_ss = math.fsum((x - left_mean) ** 2 for x in left)
    right_ss = math.fsum((y - right_mean) ** 2 for y in right)
    return covariance / math.sqrt(left_ss * right_ss)


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
    spreads = [(two_year - ten_year) * 100 for _, two_year, ten_year in rows]
    changes = [float(current - previous) for previous, current in zip(spreads, spreads[1:])]
    predictors = changes[:-1]
    outcomes = changes[1:]
    nonzero_pairs = sum(left * right != 0 for left, right in zip(predictors, outcomes, strict=True))
    opposite_pairs = sum(left * right < 0 for left, right in zip(predictors, outcomes, strict=True))
    evidence = {
        "lag1_pearson_correlation": round(correlation(predictors, outcomes), 12),
        "mean_spread_change_bps": round(math.fsum(changes) / len(changes), 12),
        "opposite_nonzero_direction_rate": round(opposite_pairs / nonzero_pairs, 12) if nonzero_pairs else 0.0,
    }

    start = date.fromisoformat(spec["data"]["period_start"])
    end = date.fromisoformat(spec["data"]["period_end"])
    minimum_rows = spec["data"]["minimum_rows"]
    maximum_rows = spec["data"]["maximum_rows"]
    minimum_pairs = spec["decision_rule"]["minimum_lag_pairs"]
    maximum_correlation = spec["decision_rule"]["maximum_lag1_correlation"]
    expected_pass = (
        minimum_rows <= len(rows) <= maximum_rows
        and missing == 0
        and dates == sorted(set(dates))
        and all(start <= observed <= end for observed in dates)
        and len(predictors) >= minimum_pairs
        and evidence["lag1_pearson_correlation"] <= maximum_correlation
    )

    failures = []
    if evidence != recorded["evidence"]:
        failures.append("recorded evidence differs from independent recalculation")
    if hashlib.sha256(raw).hexdigest() != recorded["data"]["snapshot_sha256"]:
        failures.append("holdout snapshot hash differs from record")
    if len(raw) != recorded["data"]["snapshot_bytes"] or len(rows) != recorded["data"]["rows"]:
        failures.append("holdout byte or row count differs from record")
    if len(predictors) != recorded["method"]["lag_pairs"]:
        failures.append("lag-pair count differs from record")
    if recorded["preregistration_commit"] != PREREGISTRATION_COMMIT:
        failures.append("unexpected preregistration commit")
    if expected_pass != (recorded["result"]["status"] == "PASS"):
        failures.append("recorded decision differs from locked threshold")
    if recorded["capital_authorized"] or recorded["strategy_mining_authorized"]:
        failures.append("record improperly authorizes strategy mining or capital")

    if failures:
        print("independent_temporal_hypothesis_audit=FAIL", file=sys.stderr)
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    print("independent_temporal_hypothesis_audit=PASS")
    print(json.dumps({"rows": len(rows), "lag_pairs": len(predictors), **evidence}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
