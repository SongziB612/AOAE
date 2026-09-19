"""Deterministic maker-plus-taker completion economics for a superhedge."""

import json
import math
from pathlib import Path
import sys

from aoae.experiment import write_record


def break_even_price(maker_cost: float, fee_rate: float) -> float:
    # maker_cost + p + fee_rate * p * (1 - p) == 1
    a, b, c = fee_rate, -(1 + fee_rate), 1 - maker_cost
    discriminant = b * b - 4 * a * c
    return (-b - math.sqrt(discriminant)) / (2 * a) if fee_rate else 1 - maker_cost


def main() -> int:
    if len(sys.argv) != 5:
        raise SystemExit("usage: evaluate_hybrid_completion.py SPEC FILL_RESULT QUEUE_RESULT OUTPUT")
    spec_path, fill_path, queue_path, output = map(Path, sys.argv[1:])
    spec = json.loads(spec_path.read_bytes())
    fill = json.loads(fill_path.read_bytes())
    queue = json.loads(queue_path.read_bytes())
    if spec.get("orders_authorized") is not False or spec.get("capital_authorized") is not False:
        raise ValueError("hybrid diagnostic requires zero orders and zero capital")
    bids = {leg["name"]: float(leg["paper_bid"]) for leg in fill["legs"]}
    books = {leg["name"]: leg for leg in queue["legs"]}
    completion = spec["completion_leg"]
    maker_legs = spec["maker_legs"]
    maker_cost = sum(bids[name] for name in maker_legs)
    taker_price = float(books[completion]["current_best_ask"])
    rate = float(spec["taker_fee_rate"])
    fee = rate * taker_price * (1 - taker_price)
    total = maker_cost + taker_price + fee
    payoff = float(spec["minimum_terminal_payoff_per_set"])
    margin = payoff - total
    size = float(spec["diagnostic_set_size"])
    record = {
        "schema_version": 1,
        "record_type": "hybrid_superhedge_completion_diagnostic",
        "method": {
            "maker_legs": maker_legs,
            "completion_leg": completion,
            "completion_order_assumption": "Immediate taker buy only after all three maker legs fill; price and displayed size can change before then.",
            "taker_fee_formula": "rate * price * (1 - price)",
            "orders_placed": 0,
            "authentication_used": False,
        },
        "economics_per_set": {
            "maker_cost": round(maker_cost, 8),
            "completion_taker_price": round(taker_price, 8),
            "completion_taker_fee": round(fee, 8),
            "total_cost": round(total, 8),
            "minimum_terminal_payoff": payoff,
            "locked_margin_if_completed_at_observed_ask": round(margin, 8),
            "return_on_completed_cost": round(margin / total, 8),
            "break_even_completion_price_including_fee": round(break_even_price(maker_cost, rate), 8),
            "worst_case_loss_before_completion": round(maker_cost, 8),
        },
        "minimum_size_diagnostic": {
            "sets": size,
            "capital_if_completed": round(size * total, 8),
            "profit_if_completed": round(size * margin, 8),
            "worst_case_loss_before_completion": round(size * maker_cost, 8),
        },
        "result": {
            "positive_at_observed_completion_ask": margin > 0,
            "execution_candidate": margin > 0,
            "interpretation": "Positive completion arithmetic does not establish that maker legs fill, that the completion ask persists, or that cross-market resolutions remain consistent.",
        },
        "capital_authorized": False,
        "decision": "forward_monitor_three_maker_legs" if margin > 0 else "reject",
    }
    write_record(output, record)
    print(json.dumps(record["economics_per_set"] | record["minimum_size_diagnostic"] | record["result"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
