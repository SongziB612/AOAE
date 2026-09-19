"""Fail-closed admission and allocation for independent economic edges."""

from __future__ import annotations

from typing import Any


def assess_edge(edge: dict[str, Any]) -> dict[str, Any]:
    """Evaluate an edge against its preregistered autonomous-allocation gates."""
    attempts = int(edge["execution_attempts"])
    fills = int(edge["execution_fills"])
    fill_rate = fills / attempts if attempts else 0.0
    pnl = edge.get("forward_net_pnl_after_costs")
    lcb = edge.get("selection_adjusted_mean_pnl_lcb")
    checks = {
        "minimum_forward_observations": int(edge["forward_observations"]) >= int(edge["minimum_forward_observations"]),
        "positive_forward_net_pnl": pnl is not None and float(pnl) > 0,
        "positive_selection_adjusted_lcb": lcb is not None and float(lcb) > 0,
        "selection_bias_accounted": edge["selection_bias_accounted"] is True,
        "independent_audit_passed": edge["independent_audit_passed"] is True,
        "execution_reconciled": edge["execution_reconciled"] is True,
        "minimum_execution_fill_rate": attempts > 0 and fill_rate >= float(edge["minimum_execution_fill_rate"]),
        "capacity_estimated": edge.get("estimated_capacity_cny") is not None and float(edge["estimated_capacity_cny"]) > 0,
        "risk_limit_intact": edge["risk_limit_breached"] is False,
        "forward_only": edge["forward_only"] is True,
    }
    admitted = all(checks.values())
    return {
        "edge_id": edge["edge_id"],
        "strategy_family": edge["strategy_family"],
        "mechanism": edge["mechanism"],
        "evidence_state": edge["evidence_state"],
        "fill_rate": fill_rate,
        "checks": checks,
        "failed_checks": [name for name, passed in checks.items() if not passed],
        "admitted_to_autonomous_portfolio": admitted,
        "maximum_allocation_fraction": float(edge["maximum_allocation_fraction"]) if admitted else 0.0,
    }


def allocate_edges(edges: list[dict[str, Any]], gross_exposure_cap: float) -> dict[str, Any]:
    """Equal-risk placeholder with hard caps; never lever and never force an edge."""
    if not 0 <= gross_exposure_cap <= 1:
        raise ValueError("gross exposure cap must be between zero and one")
    assessments = [assess_edge(edge) for edge in edges]
    admitted = [item for item in assessments if item["admitted_to_autonomous_portfolio"]]
    if not admitted:
        return {
            "assessments": assessments,
            "allocations": {"cash": 1.0},
            "gross_exposure": 0.0,
            "autonomous_portfolio_ready": False,
            "leverage_allowed": False,
        }
    remaining = gross_exposure_cap
    allocations: dict[str, float] = {}
    active = list(admitted)
    while active and remaining > 1e-12:
        equal_share = remaining / len(active)
        next_active = []
        distributed = 0.0
        for item in active:
            already = allocations.get(item["edge_id"], 0.0)
            room = item["maximum_allocation_fraction"] - already
            amount = min(equal_share, max(room, 0.0))
            allocations[item["edge_id"]] = already + amount
            distributed += amount
            if room - amount > 1e-12:
                next_active.append(item)
        if distributed <= 1e-12:
            break
        remaining -= distributed
        active = next_active
    gross = sum(allocations.values())
    allocations["cash"] = 1.0 - gross
    return {
        "assessments": assessments,
        "allocations": allocations,
        "gross_exposure": gross,
        "autonomous_portfolio_ready": True,
        "leverage_allowed": False,
    }
