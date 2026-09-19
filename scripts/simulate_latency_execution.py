"""Apply preregistered fixed delays to an immutable WebSocket probe."""

import hashlib
import json
from pathlib import Path
import sys

from aoae.experiment import write_record
from aoae.latency_probe import simulate_delayed_taker


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit("usage: simulate_latency_execution.py SPEC SOURCE_RESULT OUTPUT")
    spec_path, source_path, output = map(Path, sys.argv[1:])
    spec_bytes, source_bytes = spec_path.read_bytes(), source_path.read_bytes()
    spec, source = json.loads(spec_bytes), json.loads(source_bytes)
    if any(spec.get(key) is not False for key in ("orders_authorized", "authentication_authorized", "capital_authorized")):
        raise ValueError("simulation requires zero orders, zero authentication, and zero capital")
    if source.get("capital_authorized") is not False or source["method"].get("book_transport") != "websocket":
        raise ValueError("source must be a read-only WebSocket probe")
    snapshots = source["evidence"]["book_snapshots"]
    rate, exponent = float(source["fee"]["rate"]), float(source["fee"]["exponent"])
    simulations = []
    for point in source["decision_points"]:
        if point["seconds_before_end"] not in spec["decision_seconds_before_end"]:
            continue
        for delay in spec["delays_ms"]:
            simulations.append({"seconds_before_end": point["seconds_before_end"], **simulate_delayed_taker(snapshots, point, int(delay), float(spec["shares_per_attempt"]), rate, exponent)})
    record = {
        "schema_version": 1,
        "record_type": "read_only_websocket_execution_delay_simulation",
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "simulations": simulations,
        "summary": {
            "simulated_reprices": sum(item["status"] == "SIMULATED_REPRICE" for item in simulations),
            "positive_reprices": sum(item.get("net_pnl", 0) > 0 for item in simulations),
            "net_pnl_sum_across_all_diagnostics": sum(item.get("net_pnl", 0) for item in simulations),
            "deployable": False,
        },
        "orders_placed": 0,
        "authentication_used": False,
        "capital_authorized": False,
        "decision": "engineering_only_collect_more_websocket_markets",
    }
    write_record(output, record)
    print(json.dumps(record["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
