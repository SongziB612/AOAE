"""Multi-seed sensitivity runner with aggregate, preregistered gates."""

from __future__ import annotations

from dataclasses import replace
import math
import statistics
from typing import Any, Sequence

from aoae.contracts import ExperimentSpec
from aoae.experiment import run_experiment
from aoae.sensitivity_contracts import SensitivitySpec


_Z_95 = 1.959963984540054


def wilson_lower_bound_95(successes: int, trials: int) -> float:
    if trials <= 0 or successes < 0 or successes > trials:
        raise ValueError("successes and trials must satisfy 0 <= successes <= trials")
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


def _distribution(values: Sequence[float]) -> dict[str, float]:
    if not values:
        raise ValueError("distribution requires at least one value")
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


def run_sensitivity(spec: SensitivitySpec, base_spec: ExperimentSpec) -> dict[str, Any]:
    seed_records: list[dict[str, int | float | str | bool]] = []
    structured_means: list[float] = []
    control_means: list[float] = []
    advantages: list[float] = []

    for seed in spec.seeds:
        seeded_data = replace(base_spec.data, seed=seed)
        seeded_spec = replace(base_spec, data=seeded_data)
        base_record = run_experiment(seeded_spec)
        structured = base_record["evidence"]["metrics"]["structured"]["out_of_sample"]
        control = base_record["evidence"]["metrics"]["control"]["out_of_sample"]
        structured_mean = float(structured["mean_net_return"])
        control_mean = float(control["mean_net_return"])
        advantage = round(structured_mean - control_mean, 12)
        seed_passed = base_record["result"]["status"] == "PASS"
        structured_means.append(structured_mean)
        control_means.append(control_mean)
        advantages.append(advantage)
        seed_records.append(
            {
                "seed": seed,
                "status": "PASS" if seed_passed else "FAIL",
                "structured_oos_mean_net_return": structured_mean,
                "structured_oos_cumulative_net_return": structured["cumulative_net_return"],
                "control_oos_mean_net_return": control_mean,
                "mean_net_return_advantage": advantage,
            }
        )

    pass_count = sum(record["status"] == "PASS" for record in seed_records)
    seed_count = len(seed_records)
    pass_rate = round(pass_count / seed_count, 12)
    lower_bound = wilson_lower_bound_95(pass_count, seed_count)
    rate_check = pass_rate >= spec.acceptance.minimum_seed_pass_rate
    lower_bound_check = lower_bound >= spec.acceptance.minimum_wilson_lower_bound
    passed = rate_check and lower_bound_check

    return {
        "schema_version": 1,
        "experiment_id": spec.experiment_id,
        "record_type": "synthetic_multiseed_sensitivity_gate",
        "hypothesis": spec.hypothesis,
        "base_experiment": {
            "experiment_id": base_spec.experiment_id,
            "canonical_spec_sha256": spec.base_spec_digest,
            "seed_override_only": True,
        },
        "method": {
            "seed_policy": "preregistered_exhaustive_no_filtering",
            "declared_seed_count": seed_count,
            "confidence_interval": "two_sided_wilson_95_percent",
            "minimum_seed_pass_rate": spec.acceptance.minimum_seed_pass_rate,
            "minimum_wilson_lower_bound": spec.acceptance.minimum_wilson_lower_bound,
            "bias_controls": list(spec.bias_controls),
        },
        "evidence": {
            "seed_results": seed_records,
            "aggregate": {
                "seed_count": seed_count,
                "pass_count": pass_count,
                "failure_count": seed_count - pass_count,
                "pass_rate": pass_rate,
                "wilson_lower_bound_95": lower_bound,
                "structured_oos_mean_net_return": _distribution(structured_means),
                "control_oos_mean_net_return": _distribution(control_means),
                "mean_net_return_advantage": _distribution(advantages),
            },
        },
        "result": {
            "status": "PASS" if passed else "FAIL",
            "checks": {
                "seed_pass_rate_at_least_minimum": rate_check,
                "wilson_lower_bound_at_least_minimum": lower_bound_check,
            },
            "interpretation": (
                "The deliberately injected structure survived the preregistered seed sensitivity gate. "
                "This validates infrastructure stability only, not a market edge."
                if passed
                else "The reference result was too seed-sensitive for the preregistered gate."
            ),
        },
        "failure_modes": list(spec.failure_modes),
        "confidence": spec.confidence,
        "decision": "multiseed_infrastructure_validated" if passed else "multiseed_infrastructure_failed",
        "capital_authorized": spec.capital_authorized,
        "next_experiment": spec.next_experiment,
    }
