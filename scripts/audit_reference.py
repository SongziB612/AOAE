"""Independent, standard-library recalculation of EXP-0001.

This deliberately does not import AOAE implementation modules. It exists to catch
shared mistakes that a test calling the production runner would miss.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import random
import sys


ROOT = Path(__file__).parents[1]
EXPERIMENT = ROOT / "research" / "experiments" / "0001-synthetic-mean-reversion"


def independent_oos_metrics(
    innovations: list[float],
    phi: float,
    cost_bps: float,
    split_index: int,
) -> dict[str, float]:
    returns: list[float] = []
    prior_return = 0.0
    for innovation in innovations:
        current_return = phi * prior_return + innovation
        returns.append(current_return)
        prior_return = current_return

    previous_position = 0.0
    net_returns: list[float] = []
    for index, market_return in enumerate(returns):
        if index == 0 or returns[index - 1] == 0:
            position = 0.0
        else:
            position = -math.copysign(1.0, returns[index - 1])
        turnover = abs(position - previous_position)
        net_return = position * market_return - turnover * cost_bps / 10_000.0
        if index >= split_index:
            net_returns.append(net_return)
        previous_position = position

    equity = math.prod(1.0 + value for value in net_returns)
    return {
        "mean_net_return": round(math.fsum(net_returns) / len(net_returns), 12),
        "cumulative_net_return": round(equity - 1.0, 12),
    }


def main() -> int:
    spec = json.loads((EXPERIMENT / "spec.json").read_text(encoding="utf-8"))
    expected = json.loads((EXPERIMENT / "result.json").read_text(encoding="utf-8"))
    data = spec["data"]
    method = spec["method"]
    rng = random.Random(data["seed"])
    innovations = [rng.gauss(0.0, data["sigma"]) for _ in range(data["samples"])]
    split_index = int(data["samples"] * method["train_fraction"])

    independently_calculated = {
        "structured": independent_oos_metrics(
            innovations,
            data["structured_phi"],
            method["cost_bps"],
            split_index,
        ),
        "control": independent_oos_metrics(
            innovations,
            data["control_phi"],
            method["cost_bps"],
            split_index,
        ),
    }

    failures: list[str] = []
    for label, metrics in independently_calculated.items():
        recorded = expected["evidence"]["metrics"][label]["out_of_sample"]
        for metric_name, actual in metrics.items():
            if actual != recorded[metric_name]:
                failures.append(
                    f"{label}.{metric_name}: recorded={recorded[metric_name]} independent={actual}"
                )

    if failures:
        print("independent_audit=FAIL", file=sys.stderr)
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    print("independent_audit=PASS")
    print(json.dumps(independently_calculated, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
