"""Fail-closed capital-readiness assessment."""

from __future__ import annotations

from typing import Any


PASS = "PASS"


def resolve_json_path(record: dict[str, Any], path: list[str]) -> Any:
    """Resolve a strict object-only JSON path used by evidence assertions."""
    value: Any = record
    for key in path:
        if not isinstance(value, dict) or key not in value:
            raise ValueError(f"missing assertion path: {'.'.join(path)}")
        value = value[key]
    return value


def evaluate_condition(observed: Any, operator: str, expected: Any) -> bool:
    """Evaluate a small, explicit predicate language for derived gates."""
    if operator == "equals":
        return observed == expected
    if operator == "gte":
        return observed >= expected
    if operator == "lte":
        return observed <= expected
    if operator == "gt":
        return observed > expected
    if operator == "in":
        return observed in expected
    raise ValueError(f"unsupported condition operator: {operator}")


def apply_derived_rule(gate: dict[str, Any], evidence_records: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Return a gate whose status is activated and evaluated from bound JSON evidence."""
    result = dict(gate)
    derived = result.get("derived_rule")
    if not derived:
        return result

    def passes(condition: dict[str, Any]) -> bool:
        record = evidence_records[condition["source"]]
        observed = resolve_json_path(record, condition["path"])
        return evaluate_condition(observed, condition["operator"], condition["value"])

    if all(passes(condition) for condition in derived["activate_when"]):
        result["status"] = PASS if all(passes(condition) for condition in derived["pass_when"]) else "FAIL"
    return result


def assess_capital_readiness(gates: list[dict[str, Any]]) -> dict[str, Any]:
    """Separate completed preparation from time/account/user-controlled gates."""
    if not gates:
        raise ValueError("at least one gate is required")
    identifiers = [gate["id"] for gate in gates]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("gate ids must be unique")
    for gate in gates:
        if not gate.get("evidence"):
            raise ValueError(f"gate lacks evidence: {gate['id']}")
    failed = [gate for gate in gates if gate["status"] == "FAIL"]
    incomplete = [gate for gate in gates if gate["status"] != PASS]
    externally_blocked = [
        gate for gate in incomplete
        if gate["status"] in {"PENDING_EXTERNAL_TIME", "PENDING_EXTERNAL_ACCOUNT", "PENDING_USER_APPROVAL"}
    ]
    internally_incomplete = [gate for gate in incomplete if gate not in externally_blocked and gate not in failed]
    return {
        "gate_count": len(gates),
        "passed_count": len(gates) - len(incomplete),
        "failed_gate_ids": [gate["id"] for gate in failed],
        "incomplete_gate_ids": [gate["id"] for gate in incomplete],
        "external_gate_ids": [gate["id"] for gate in externally_blocked],
        "internal_incomplete_gate_ids": [gate["id"] for gate in internally_incomplete],
        "all_controllable_preparation_complete": not failed and not internally_incomplete,
        "ready_for_capital": not incomplete,
        "capital_authorized": False,
    }
