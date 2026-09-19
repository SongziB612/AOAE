"""Independent-IID negative-control contract and rejection experiment."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import random
import re
import statistics
from typing import Any, Sequence

from aoae.contracts import ContractError
from aoae.experiment import apply_strategy, calculate_metrics
from aoae.sensitivity_contracts import canonical_content_digest


_Z_95 = 1.959963984540054


@dataclass(frozen=True)
class NegativeControlSpec:
    experiment_id: str
    title: str
    hypothesis: str
    seed_source_path: str
    seed_source_digest: str
    seeds: tuple[int, ...]
    samples: int
    sigma: float
    control_seed_offset: int
    train_fraction: float
    cost_bps: float
    annualization_periods: int
    maximum_false_positive_rate: float
    maximum_wilson_upper_bound: float
    bias_controls: tuple[str, ...]
    failure_modes: tuple[str, ...]
    confidence: str
    capital_authorized: bool
    next_experiment: str


def _exact(value: dict[str, Any], keys: set[str], location: str) -> None:
    missing = sorted(keys - value.keys())
    extra = sorted(value.keys() - keys)
    if missing or extra:
        raise ContractError(f"{location} keys invalid: missing={missing} unexpected={extra}")


def _object(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{location} must be an object")
    return value


def _text(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{location} must be non-empty text")
    return value.strip()


def _integer(value: Any, location: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractError(f"{location} must be an integer")
    return value


def _number(value: Any, location: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"{location} must be a number")
    return float(value)


def _texts(value: Any, location: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ContractError(f"{location} must be a non-empty list")
    return tuple(_text(item, f"{location}[{index}]") for index, item in enumerate(value))


def load_negative_control_spec(path: Path) -> NegativeControlSpec:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid JSON in {path}: {exc}") from exc
    root = _object(raw, "spec")
    _exact(
        root,
        {
            "schema_version", "experiment_id", "title", "hypothesis", "seed_source",
            "data", "method", "acceptance", "bias_controls", "failure_modes",
            "confidence", "capital_authorized", "next_experiment",
        },
        "spec",
    )
    if _integer(root["schema_version"], "schema_version") != 1:
        raise ContractError("schema_version must be 1")
    experiment_id = _text(root["experiment_id"], "experiment_id")
    if not re.fullmatch(r"EXP-\d{4}-[a-z0-9-]+", experiment_id):
        raise ContractError("invalid experiment_id")

    source = _object(root["seed_source"], "seed_source")
    _exact(source, {"spec_path", "canonical_sha256"}, "seed_source")
    source_path_text = _text(source["spec_path"], "seed_source.spec_path")
    source_digest = _text(source["canonical_sha256"], "seed_source.canonical_sha256")
    if Path(source_path_text).is_absolute() or not re.fullmatch(r"[0-9a-f]{64}", source_digest):
        raise ContractError("seed source path or digest is invalid")
    source_path = (path.parent / source_path_text).resolve()
    experiments_root = path.parent.parent.resolve()
    if experiments_root != source_path.parent.parent or experiments_root not in source_path.parents:
        raise ContractError("seed source must remain inside the experiments directory")
    source_raw = json.loads(source_path.read_text(encoding="utf-8"))
    if canonical_content_digest(source_raw) != source_digest:
        raise ContractError("seed source digest mismatch")
    seeds = tuple(_integer(seed, "seed_source.seeds") for seed in source_raw.get("seeds", []))
    if len(seeds) < 20 or len(set(seeds)) != len(seeds):
        raise ContractError("seed source must contain at least 20 unique seeds")

    data = _object(root["data"], "data")
    _exact(data, {"samples", "sigma", "control_seed_offset"}, "data")
    samples = _integer(data["samples"], "data.samples")
    sigma = _number(data["sigma"], "data.sigma")
    offset = _integer(data["control_seed_offset"], "data.control_seed_offset")
    if samples < 100 or sigma <= 0 or offset == 0:
        raise ContractError("negative-control data parameters are invalid")

    method = _object(root["method"], "method")
    _exact(method, {"strategy", "signal_lag", "train_fraction", "cost_bps", "annualization_periods"}, "method")
    if _text(method["strategy"], "method.strategy") != "lagged_sign_reversal" or _integer(method["signal_lag"], "method.signal_lag") != 1:
        raise ContractError("version 1 requires lagged_sign_reversal with signal_lag=1")
    train_fraction = _number(method["train_fraction"], "method.train_fraction")
    cost_bps = _number(method["cost_bps"], "method.cost_bps")
    annualization = _integer(method["annualization_periods"], "method.annualization_periods")
    if not 0.5 <= train_fraction <= 0.9 or cost_bps < 0 or annualization <= 0:
        raise ContractError("negative-control method parameters are invalid")

    acceptance = _object(root["acceptance"], "acceptance")
    _exact(acceptance, {"maximum_false_positive_rate", "confidence_level", "maximum_wilson_upper_bound"}, "acceptance")
    max_rate = _number(acceptance["maximum_false_positive_rate"], "acceptance.maximum_false_positive_rate")
    confidence_level = _number(acceptance["confidence_level"], "acceptance.confidence_level")
    max_upper = _number(acceptance["maximum_wilson_upper_bound"], "acceptance.maximum_wilson_upper_bound")
    if confidence_level != 0.95 or not 0 <= max_rate < max_upper <= 1:
        raise ContractError("negative-control acceptance parameters are invalid")
    if root["capital_authorized"] is not False:
        raise ContractError("negative-control research must set capital_authorized to false")

    return NegativeControlSpec(
        experiment_id=experiment_id,
        title=_text(root["title"], "title"),
        hypothesis=_text(root["hypothesis"], "hypothesis"),
        seed_source_path=source_path_text,
        seed_source_digest=source_digest,
        seeds=seeds,
        samples=samples,
        sigma=sigma,
        control_seed_offset=offset,
        train_fraction=train_fraction,
        cost_bps=cost_bps,
        annualization_periods=annualization,
        maximum_false_positive_rate=max_rate,
        maximum_wilson_upper_bound=max_upper,
        bias_controls=_texts(root["bias_controls"], "bias_controls"),
        failure_modes=_texts(root["failure_modes"], "failure_modes"),
        confidence=_text(root["confidence"], "confidence"),
        capital_authorized=False,
        next_experiment=_text(root["next_experiment"], "next_experiment"),
    )


def wilson_upper_bound_95(successes: int, trials: int) -> float:
    if trials <= 0 or not 0 <= successes <= trials:
        raise ValueError("successes and trials must satisfy 0 <= successes <= trials")
    proportion = successes / trials
    z_squared = _Z_95**2
    denominator = 1.0 + z_squared / trials
    center = (proportion + z_squared / (2.0 * trials)) / denominator
    margin = _Z_95 * math.sqrt(proportion * (1.0 - proportion) / trials + z_squared / (4.0 * trials**2)) / denominator
    return round(min(1.0, center + margin), 12)


def _distribution(values: Sequence[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "minimum": round(ordered[0], 12),
        "median": round(statistics.median(ordered), 12),
        "maximum": round(ordered[-1], 12),
        "mean": round(math.fsum(ordered) / len(ordered), 12),
        "sample_standard_deviation": round(statistics.stdev(ordered), 12),
    }


def _iid(seed: int, samples: int, sigma: float) -> list[float]:
    rng = random.Random(seed)
    return [rng.gauss(0.0, sigma) for _ in range(samples)]


def _oos_metrics(returns: list[float], spec: NegativeControlSpec) -> dict[str, int | float]:
    applied = apply_strategy(returns, spec.cost_bps)
    start = int(spec.samples * spec.train_fraction)
    return calculate_metrics(
        applied["gross_returns"][start:], applied["net_returns"][start:],
        applied["turnovers"][start:], applied["costs"][start:], spec.annualization_periods,
    )


def run_negative_control(spec: NegativeControlSpec) -> dict[str, Any]:
    seed_results: list[dict[str, Any]] = []
    candidate_means: list[float] = []
    control_means: list[float] = []
    for seed in spec.seeds:
        candidate = _oos_metrics(_iid(seed, spec.samples, spec.sigma), spec)
        control = _oos_metrics(_iid(seed + spec.control_seed_offset, spec.samples, spec.sigma), spec)
        false_positive = candidate["cumulative_net_return"] > 0 and candidate["mean_net_return"] > control["mean_net_return"]
        candidate_means.append(float(candidate["mean_net_return"]))
        control_means.append(float(control["mean_net_return"]))
        seed_results.append({
            "seed": seed,
            "false_positive": false_positive,
            "candidate_oos_mean_net_return": candidate["mean_net_return"],
            "candidate_oos_cumulative_net_return": candidate["cumulative_net_return"],
            "control_oos_mean_net_return": control["mean_net_return"],
        })

    false_count = sum(item["false_positive"] for item in seed_results)
    seed_count = len(seed_results)
    false_rate = round(false_count / seed_count, 12)
    upper = wilson_upper_bound_95(false_count, seed_count)
    rate_check = false_rate <= spec.maximum_false_positive_rate
    upper_check = upper <= spec.maximum_wilson_upper_bound
    passed = rate_check and upper_check
    return {
        "schema_version": 1,
        "experiment_id": spec.experiment_id,
        "record_type": "independent_iid_negative_control",
        "hypothesis": spec.hypothesis,
        "method": {
            "data": "independent_iid_gaussian_candidate_and_control",
            "seed_source_sha256": spec.seed_source_digest,
            "seed_count": seed_count,
            "samples_per_series": spec.samples,
            "sigma": spec.sigma,
            "control_seed_offset": spec.control_seed_offset,
            "strategy": "lagged_sign_reversal",
            "signal_lag": 1,
            "train_fraction": spec.train_fraction,
            "cost_bps_per_unit_turnover": spec.cost_bps,
            "bias_controls": list(spec.bias_controls),
        },
        "evidence": {
            "seed_results": seed_results,
            "aggregate": {
                "seed_count": seed_count,
                "false_positive_count": false_count,
                "false_positive_rate": false_rate,
                "wilson_upper_bound_95": upper,
                "candidate_oos_mean_net_return": _distribution(candidate_means),
                "control_oos_mean_net_return": _distribution(control_means),
            },
        },
        "result": {
            "status": "PASS" if passed else "FAIL",
            "checks": {
                "false_positive_rate_at_most_maximum": rate_check,
                "wilson_upper_bound_at_most_maximum": upper_check,
            },
            "interpretation": (
                "The research rule rejected the independent IID null at the preregistered aggregate gate. "
                "This validates a negative control only, not a market edge."
                if passed else "The research rule produced too many false positives on IID noise."
            ),
        },
        "failure_modes": list(spec.failure_modes),
        "confidence": spec.confidence,
        "decision": "negative_control_rejected" if passed else "negative_control_failed",
        "capital_authorized": spec.capital_authorized,
        "next_experiment": spec.next_experiment,
    }
