"""Build the fail-closed multi-edge portfolio status record."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from aoae.edge_portfolio import allocate_edges
from aoae.experiment import write_record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    spec_bytes = args.spec.read_bytes()
    candidate_bytes = args.candidates.read_bytes()
    spec = json.loads(spec_bytes)
    candidates = json.loads(candidate_bytes)
    if any(spec.get(key) is not False for key in ("orders_authorized", "capital_authorized", "broker_connection_authorized")):
        raise ValueError("edge portfolio research cannot authorize accounts, orders, or capital")
    source_hashes = {}
    for edge in candidates["edges"]:
        sources = edge.get("evidence_sources") or []
        if not sources:
            raise ValueError(f"edge has no bound evidence sources: {edge['edge_id']}")
        source_hashes[edge["edge_id"]] = {}
        for source in sources:
            path = Path(source)
            if not path.is_file():
                raise FileNotFoundError(f"missing evidence source for {edge['edge_id']}: {source}")
            source_hashes[edge["edge_id"]][source] = hashlib.sha256(path.read_bytes()).hexdigest()
    portfolio = allocate_edges(candidates["edges"], float(spec["gross_exposure_cap"]))
    record = {
        "schema_version": 1,
        "record_type": "autonomous_edge_portfolio_status",
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "spec_sha256": hashlib.sha256(spec_bytes).hexdigest(),
        "candidates_sha256": hashlib.sha256(candidate_bytes).hexdigest(),
        "evidence_source_sha256": source_hashes,
        **portfolio,
        "decision": "RESEARCH_MORE_ALL_CASH" if not portfolio["autonomous_portfolio_ready"] else "PAPER_PORTFOLIO_ONLY",
        "orders_authorized": False,
        "capital_authorized": False,
        "broker_connection_authorized": False,
    }
    write_record(args.output, record)
    print(json.dumps({"decision": record["decision"], "allocations": record["allocations"], "admitted": sum(item["admitted_to_autonomous_portfolio"] for item in record["assessments"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
