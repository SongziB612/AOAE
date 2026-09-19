"""Independent recalculation of EXP-0003 without importing AOAE modules."""

from __future__ import annotations

import json
import math
from pathlib import Path
import random
import statistics
import sys

from audit_reference import independent_oos_metrics


ROOT = Path(__file__).parents[1]
EXPERIMENT = ROOT / "research" / "experiments" / "0003-iid-negative-control"
_Z_95 = 1.959963984540054


def upper_bound(successes: int, trials: int) -> float:
    proportion = successes / trials
    z_squared = _Z_95**2
    denominator = 1.0 + z_squared / trials
    center = (proportion + z_squared / (2.0 * trials)) / denominator
    margin = _Z_95 * math.sqrt(proportion * (1.0 - proportion) / trials + z_squared / (4.0 * trials**2)) / denominator
    return round(min(1.0, center + margin), 12)


def distribution(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "minimum": round(ordered[0], 12),
        "median": round(statistics.median(ordered), 12),
        "maximum": round(ordered[-1], 12),
        "mean": round(math.fsum(ordered) / len(ordered), 12),
        "sample_standard_deviation": round(statistics.stdev(ordered), 12),
    }


def main() -> int:
    spec = json.loads((EXPERIMENT / "spec.json").read_text(encoding="utf-8"))
    recorded = json.loads((EXPERIMENT / "result.json").read_text(encoding="utf-8"))
    seed_source_path = (EXPERIMENT / spec["seed_source"]["spec_path"]).resolve()
    seed_source = json.loads(seed_source_path.read_text(encoding="utf-8"))
    seeds = seed_source["seeds"]
    data = spec["data"]
    method = spec["method"]
    split_index = int(data["samples"] * method["train_fraction"])

    failures: list[str] = []
    false_count = 0
    candidate_means: list[float] = []
    control_means: list[float] = []
    recorded_seeds = recorded["evidence"]["seed_results"]
    if [item["seed"] for item in recorded_seeds] != seeds:
        failures.append("recorded seed order differs from seed source")

    for index, seed in enumerate(seeds):
        candidate_rng = random.Random(seed)
        candidate_innovations = [candidate_rng.gauss(0.0, data["sigma"]) for _ in range(data["samples"])]
        control_rng = random.Random(seed + data["control_seed_offset"])
        control_innovations = [control_rng.gauss(0.0, data["sigma"]) for _ in range(data["samples"])]
        candidate = independent_oos_metrics(candidate_innovations, 0.0, method["cost_bps"], split_index)
        control = independent_oos_metrics(control_innovations, 0.0, method["cost_bps"], split_index)
        false_positive = candidate["cumulative_net_return"] > 0 and candidate["mean_net_return"] > control["mean_net_return"]
        false_count += false_positive
        candidate_means.append(candidate["mean_net_return"])
        control_means.append(control["mean_net_return"])

        expected = recorded_seeds[index]
        checks = {
            "candidate_oos_mean_net_return": candidate["mean_net_return"],
            "candidate_oos_cumulative_net_return": candidate["cumulative_net_return"],
            "control_oos_mean_net_return": control["mean_net_return"],
            "false_positive": false_positive,
        }
        for name, actual in checks.items():
            if expected[name] != actual:
                failures.append(f"seed {seed} {name}: recorded={expected[name]} independent={actual}")

    seed_count = len(seeds)
    aggregate = {
        "seed_count": seed_count,
        "false_positive_count": false_count,
        "false_positive_rate": round(false_count / seed_count, 12),
        "wilson_upper_bound_95": upper_bound(false_count, seed_count),
        "candidate_oos_mean_net_return": distribution(candidate_means),
        "control_oos_mean_net_return": distribution(control_means),
    }
    if aggregate != recorded["evidence"]["aggregate"]:
        failures.append("recorded aggregate differs from independent recalculation")

    if failures:
        print("independent_negative_control_audit=FAIL", file=sys.stderr)
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    print("independent_negative_control_audit=PASS")
    print(json.dumps({
        "seed_count": seed_count,
        "false_positive_count": false_count,
        "false_positive_rate": aggregate["false_positive_rate"],
        "wilson_upper_bound_95": aggregate["wilson_upper_bound_95"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
