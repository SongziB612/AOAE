"""Build a hash-bound, fail-closed pre-capital readiness report."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

from aoae.capital_readiness import apply_derived_rule, assess_capital_readiness, resolve_json_path
from aoae.experiment import write_record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = json.loads(args.spec.read_text(encoding="utf-8"))
    if any(raw.get(key) is not False for key in ("orders_authorized", "capital_authorized", "broker_connection_authorized")):
        raise ValueError("readiness research cannot authorize capital, orders, or accounts")
    hashes = {}
    evidence_records = {}
    gates = deepcopy(raw["gates"])
    for gate in gates:
        for source in gate["evidence"]:
            path = Path(source)
            if not path.is_file():
                raise FileNotFoundError(f"missing gate evidence: {source}")
            hashes[source] = sha256(path.read_bytes()).hexdigest()
            if path.suffix.lower() == ".json":
                evidence_records[str(path)] = json.loads(path.read_text(encoding="utf-8"))
        for assertion in gate.get("json_assertions", []):
            path = Path(assertion["source"])
            if path not in {Path(source) for source in gate["evidence"]}:
                raise ValueError(f"assertion source is not gate evidence: {path}")
            observed = resolve_json_path(evidence_records[str(path)], assertion["path"])
            if observed != assertion["equals"]:
                raise ValueError(
                    f"evidence assertion failed for {gate['id']}: "
                    f"{'.'.join(assertion['path'])}={observed!r}, expected {assertion['equals']!r}"
                )
    normalized_records = {str(Path(key)): value for key, value in evidence_records.items()}
    gates = [
        apply_derived_rule(
            {
                **gate,
                **({
                    "derived_rule": {
                        group: [{**condition, "source": str(Path(condition["source"]))} for condition in gate["derived_rule"][group]]
                        for group in ("activate_when", "pass_when")
                    }
                } if gate.get("derived_rule") else {}),
            },
            normalized_records,
        )
        for gate in gates
    ]
    assessment = assess_capital_readiness(gates)
    record = {
        "schema_version": 1,
        "record_type": "pre_capital_readiness_status",
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "spec_sha256": sha256(args.spec.read_bytes()).hexdigest(),
        "evidence_sha256": hashes,
        "pilot": raw["pilot"],
        "gates": gates,
        "assessment": assessment,
        "decision": "READY_FOR_FRESH_USER_DECISION" if assessment["ready_for_capital"] else "DO_NOT_FUND",
        "orders_authorized": False,
        "capital_authorized": False,
        "broker_connection_authorized": False,
    }
    digest = write_record(args.output, record)
    print(json.dumps({"sha256": digest, "decision": record["decision"], **assessment}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
