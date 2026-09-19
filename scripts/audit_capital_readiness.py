"""Independent standard-library audit of a generated capital-readiness record."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path


def _resolve(record, path):
    value = record
    for key in path:
        if not isinstance(value, dict) or key not in value:
            raise ValueError(f"missing JSON path: {'.'.join(path)}")
        value = value[key]
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite: {args.output}")
    spec_bytes, result_bytes = args.spec.read_bytes(), args.result.read_bytes()
    spec, result = json.loads(spec_bytes), json.loads(result_bytes)

    checks = {
        "spec_digest_matches": result["spec_sha256"] == sha256(spec_bytes).hexdigest(),
        "result_forbids_orders": result.get("orders_authorized") is False,
        "result_forbids_capital": result.get("capital_authorized") is False,
        "result_forbids_account_connection": result.get("broker_connection_authorized") is False,
        "assessment_forbids_capital": result["assessment"].get("capital_authorized") is False,
        "gate_ids_unique": len({gate["id"] for gate in result["gates"]}) == len(result["gates"]),
    }
    evidence_checks = {}
    for source, expected in result["evidence_sha256"].items():
        path = Path(source)
        evidence_checks[source] = path.is_file() and sha256(path.read_bytes()).hexdigest() == expected
    checks["all_evidence_digests_match"] = all(evidence_checks.values())

    assertion_checks = {}
    for gate in spec["gates"]:
        for index, assertion in enumerate(gate.get("json_assertions", [])):
            record = json.loads(Path(assertion["source"]).read_text(encoding="utf-8"))
            key = f"{gate['id']}:{index}"
            assertion_checks[key] = _resolve(record, assertion["path"]) == assertion["equals"]
    checks["all_static_json_assertions_match"] = all(assertion_checks.values())

    statuses = {gate["id"]: gate["status"] for gate in result["gates"]}
    passed = [identifier for identifier, status in statuses.items() if status == "PASS"]
    incomplete = [identifier for identifier, status in statuses.items() if status != "PASS"]
    external_statuses = {"PENDING_EXTERNAL_TIME", "PENDING_EXTERNAL_ACCOUNT", "PENDING_USER_APPROVAL"}
    internal = [identifier for identifier, status in statuses.items() if status not in external_statuses | {"PASS", "FAIL"}]
    failed = [identifier for identifier, status in statuses.items() if status == "FAIL"]
    checks.update({
        "reported_gate_count_matches": result["assessment"]["gate_count"] == len(statuses),
        "reported_passed_count_matches": result["assessment"]["passed_count"] == len(passed),
        "reported_incomplete_ids_match": result["assessment"]["incomplete_gate_ids"] == incomplete,
        "internal_incomplete_ids_match": result["assessment"]["internal_incomplete_gate_ids"] == internal,
        "reported_controllable_completion_matches": result["assessment"]["all_controllable_preparation_complete"] == (not internal and not failed),
        "reported_gate_ids_match_spec": set(statuses) == {gate['id'] for gate in spec['gates']},
        "static_gate_statuses_match_spec": all(statuses.get(gate['id']) == gate['status'] for gate in spec['gates'] if not gate.get('derived_rule')),
        "decision_matches_completeness": (
            (bool(incomplete) and result["decision"] == "DO_NOT_FUND")
            or (not incomplete and result["decision"] == "READY_FOR_FRESH_USER_DECISION")
        ),
    })
    passed_audit = all(checks.values())
    output = {
        "schema_version": 1,
        "record_type": "independent_capital_readiness_audit",
        "audited_result_sha256": sha256(result_bytes).hexdigest(),
        "checks": checks,
        "evidence_digest_checks": evidence_checks,
        "static_assertion_checks": assertion_checks,
        "status": "PASS" if passed_audit else "FAIL",
        "orders_authorized": False,
        "capital_authorized": False,
        "broker_connection_authorized": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": output["status"], "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if passed_audit else 1


if __name__ == "__main__":
    raise SystemExit(main())
