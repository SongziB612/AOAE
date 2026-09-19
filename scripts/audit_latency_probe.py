"""Independent fail-closed arithmetic and contract audit for a latency-probe result."""

import json
from pathlib import Path
import sys


def fee(price: float, rate: float, exponent: float) -> float:
    return rate * (price * (1 - price)) ** exponent


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: audit_latency_probe.py SPEC RESULT")
    spec, result = (json.loads(Path(path).read_bytes()) for path in sys.argv[1:])
    if any(spec.get(key) is not False for key in ("orders_authorized", "authentication_authorized", "capital_authorized")):
        raise AssertionError("spec authority lock failed")
    if result.get("capital_authorized") is not False or result["method"].get("orders_placed") != 0 or result["method"].get("authentication_used") is not False:
        raise AssertionError("result authority lock failed")
    if "bnb-usd-twap-60s-streams" not in str(result["market"].get("resolution_source")):
        raise AssertionError("unexpected resolution source")
    points = result["decision_points"]
    if [point["seconds_before_end"] for point in points] != spec["decision_seconds_before_end"]:
        raise AssertionError("decision points differ from preregistration")
    rate, exponent = float(result["fee"]["rate"]), float(result["fee"]["exponent"])
    for point in points:
        if point["status"] != "QUOTED_ONLY":
            continue
        expected_fee = fee(float(point["ask"]), rate, exponent)
        expected_pnl = (1.0 if point["signal_correct"] else 0.0) - float(point["ask"]) - expected_fee
        if abs(expected_fee - float(point["fee_per_share"])) > 1e-12 or abs(expected_pnl - float(point["quoted_net_pnl_per_share"])) > 1e-12:
            raise AssertionError("fee-adjusted PnL mismatch")
    if result["result"].get("deployable") is not False:
        raise AssertionError("engineering probe must not authorize deployment")
    print(json.dumps({"audit": "PASS", "audited_points": len(points), "deployable": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
