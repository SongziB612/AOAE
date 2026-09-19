"""Conditional capital simulation for the audited hybrid superhedge economics."""

import json
import math
from pathlib import Path
import sys

from aoae.experiment import write_record


def floor_quantity(value: float, precision: int = 2) -> float:
    scale = 10**precision
    return math.floor(value * scale) / scale


def scenario(quantity: float, total_cost: float, margin: float, pre_completion_loss: float, fx: float) -> dict:
    return {
        "sets": quantity,
        "completed_capital_cny": round(quantity * total_cost * fx, 2),
        "profit_if_completed_cny": round(quantity * margin * fx, 2),
        "worst_case_loss_before_completion_cny": round(quantity * pre_completion_loss * fx, 2),
    }


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit("usage: simulate_hybrid_capital.py SPEC ECONOMICS_RESULT OUTPUT")
    spec_path, economics_path, output = map(Path, sys.argv[1:])
    spec = json.loads(spec_path.read_bytes())
    economics = json.loads(economics_path.read_bytes())["economics_per_set"]
    if spec.get("capital_authorized") is not False:
        raise ValueError("simulation must not authorize capital")
    fx = float(spec["usd_cny"])
    capital = float(spec["capital_cny"])
    loss_limit = float(spec["maximum_loss_cny"])
    total_cost = float(economics["total_cost"])
    margin = float(economics["locked_margin_if_completed_at_observed_ask"])
    pre_loss = float(economics["worst_case_loss_before_completion"])
    full_quantity = floor_quantity((capital / fx) / total_cost)
    risk_quantity = floor_quantity((loss_limit / fx) / pre_loss)
    record = {
        "schema_version": 1,
        "record_type": "conditional_hybrid_capital_simulation",
        "assumptions": {
            "capital_cny": capital,
            "maximum_loss_cny": loss_limit,
            "usd_cny": fx,
            "fx_date": spec["fx_date"],
            "fill_probability_estimated": False,
            "prices_persist_until_completion": True,
            "external_transfer_and_withdrawal_costs_included": False,
        },
        "scenarios": {
            "minimum_five_sets": scenario(5, total_cost, margin, pre_loss, fx),
            "respect_loss_limit": scenario(risk_quantity, total_cost, margin, pre_loss, fx),
            "deploy_all_capital": scenario(full_quantity, total_cost, margin, pre_loss, fx),
            "no_fill": {"profit_cny": 0},
        },
        "interpretation": "Profits are conditional on all maker legs filling and the completion ask remaining available. Without a validated fill probability this is not an expected-return forecast.",
        "orders_placed": 0,
        "capital_authorized": False,
        "decision": "paper_only",
    }
    write_record(output, record)
    print(json.dumps(record["scenarios"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
