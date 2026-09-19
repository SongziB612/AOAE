"""Independent recalculation of every seed and aggregate in EXP-0002."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import random
import statistics
import sys

from audit_reference import independent_oos_metrics


ROOT = Path(__file__).parents[1]
EXPERIMENTS = ROOT / "research" / "experiments"
SENSITIVITY = EXPERIMENTS / "0002-multiseed-sensitivity"
_Z_95 = 1.959963984540054


def independent_wilson_lower(successes: int, trials: int) -> float:
    proportion = successes / trials
    z_squared = _Z_95**2
    denominator = 1.0 + z_squared / trials
    center = (proportion + z_squared / (2.0 * trials)) / denominator
    margin = (
        _Z_95
        * math.sqrt(proportion * (1.0 - proportion) / trials + z_squared / (4.0 * trials**2))
        / denominator
    )
    return round(max(0.0, center - margin), 12)


def independent_distribution(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)

    def percentile(fraction: float) -> float:
        index = fraction * (len(ordered) - 1)
        lower = math.floor(index)
        upper = math.ceil(index)
        if lower == upper:
            return ordered[lower]
        weight = index - lower
        return ordered[lower] * (1.0 - weight) + ordered[upper] * weight

    return {
        "minimum": round(ordered[0], 12),
        "p10": round(percentile(0.10), 12),
        "median": round(statistics.median(ordered), 12),
        "p90": round(percentile(0.90), 12),
        "maximum": round(ordered[-1], 12),
        "mean": round(math.fsum(ordered) / len(ordered), 12),
        "sample_standard_deviation": round(statistics.stdev(ordered), 12),
    }


def main() -> int:
    sensitivity = json.loads((SENSITIVITY / "spec.json").read_text(encoding="utf-8"))
    recorded = json.loads((SENSITIVITY / "result.json").read_text(encoding="utf-8"))
    base_path = (SENSITIVITY / sensitivity["base_experiment"]["spec_path"]).resolve()
    base = json.loads(base_path.read_text(encoding="utf-8"))
    canonical_base = json.dumps(base, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    actual_digest = hashlib.sha256(canonical_base.encode("utf-8")).hexdigest()

    failures: list[str] = []
    if actual_digest != sensitivity["base_experiment"]["canonical_sha256"]:
        failures.append("base experiment digest does not match the sensitivity preregistration")

    data = base["data"]
    method = base["method"]
    split_index = int(data["samples"] * method["train_fraction"])
    structured_means: list[float] = []
    control_means: list[float] = []
    advantages: list[float] = []
    pass_count = 0

    recorded_seeds = recorded["evidence"]["seed_results"]
    if [item["seed"] for item in recorded_seeds] != sensitivity["seeds"]:
        failures.append("recorded seed order differs from the preregistration")

    for index, seed in enumerate(sensitivity["seeds"]):
        rng = random.Random(seed)
        innovations = [rng.gauss(0.0, data["sigma"]) for _ in range(data["samples"])]
        structured = independent_oos_metrics(
            innovations, data["structured_phi"], method["cost_bps"], split_index
        )
        control = independent_oos_metrics(
            innovations, data["control_phi"], method["cost_bps"], split_index
        )
        advantage = round(structured["mean_net_return"] - control["mean_net_return"], 12)
        passed = (
            structured["cumulative_net_return"]
            > base["decision_rule"]["min_structured_oos_cumulative_return"]
            and structured["mean_net_return"] > control["mean_net_return"]
        )
        pass_count += passed
        structured_means.append(structured["mean_net_return"])
        control_means.append(control["mean_net_return"])
        advantages.append(advantage)

        expected_seed = recorded_seeds[index]
        checks = {
            "structured_oos_mean_net_return": structured["mean_net_return"],
            "structured_oos_cumulative_net_return": structured["cumulative_net_return"],
            "control_oos_mean_net_return": control["mean_net_return"],
            "mean_net_return_advantage": advantage,
            "status": "PASS" if passed else "FAIL",
        }
        for name, actual in checks.items():
            if expected_seed[name] != actual:
                failures.append(
                    f"seed {seed} {name}: recorded={expected_seed[name]} independent={actual}"
                )

    seed_count = len(sensitivity["seeds"])
    independent_aggregate = {
        "seed_count": seed_count,
        "pass_count": pass_count,
        "failure_count": seed_count - pass_count,
        "pass_rate": round(pass_count / seed_count, 12),
        "wilson_lower_bound_95": independent_wilson_lower(pass_count, seed_count),
        "structured_oos_mean_net_return": independent_distribution(structured_means),
        "control_oos_mean_net_return": independent_distribution(control_means),
        "mean_net_return_advantage": independent_distribution(advantages),
    }
    recorded_aggregate = recorded["evidence"]["aggregate"]
    if independent_aggregate != recorded_aggregate:
        failures.append("recorded aggregate differs from independent recalculation")

    if failures:
        print("independent_multiseed_audit=FAIL", file=sys.stderr)
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    print("independent_multiseed_audit=PASS")
    print(
        json.dumps(
            {
                "seed_count": seed_count,
                "pass_count": pass_count,
                "pass_rate": independent_aggregate["pass_rate"],
                "wilson_lower_bound_95": independent_aggregate["wilson_lower_bound_95"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
