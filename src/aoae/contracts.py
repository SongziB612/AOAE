"""Validation for versioned AOAE experiment specifications."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any


class ContractError(ValueError):
    """Raised when an experiment specification is invalid or ambiguous."""


@dataclass(frozen=True)
class DataSpec:
    kind: str
    seed: int
    samples: int
    structured_phi: float
    control_phi: float
    sigma: float


@dataclass(frozen=True)
class MethodSpec:
    strategy: str
    signal_lag: int
    train_fraction: float
    cost_bps: float
    annualization_periods: int
    trial_count: int


@dataclass(frozen=True)
class DecisionRule:
    min_structured_oos_cumulative_return: float
    require_structured_oos_mean_above_control: bool


@dataclass(frozen=True)
class ExperimentSpec:
    schema_version: int
    experiment_id: str
    title: str
    hypothesis: str
    data: DataSpec
    method: MethodSpec
    decision_rule: DecisionRule
    bias_controls: tuple[str, ...]
    failure_modes: tuple[str, ...]
    confidence: str
    capital_authorized: bool
    next_experiment: str


_TOP_LEVEL_KEYS = {
    "schema_version",
    "experiment_id",
    "title",
    "hypothesis",
    "data",
    "method",
    "decision_rule",
    "bias_controls",
    "failure_modes",
    "confidence",
    "capital_authorized",
    "next_experiment",
}


def _require_exact_keys(value: dict[str, Any], expected: set[str], location: str) -> None:
    missing = sorted(expected - value.keys())
    extra = sorted(value.keys() - expected)
    if missing or extra:
        details = []
        if missing:
            details.append(f"missing={missing}")
        if extra:
            details.append(f"unexpected={extra}")
        raise ContractError(f"{location} has invalid keys: {', '.join(details)}")


def _require_dict(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{location} must be an object")
    return value


def _require_int(value: Any, location: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractError(f"{location} must be an integer")
    return value


def _require_number(value: Any, location: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"{location} must be a number")
    return float(value)


def _require_nonempty_text(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{location} must be non-empty text")
    return value.strip()


def _require_text_list(value: Any, location: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ContractError(f"{location} must be a non-empty list")
    return tuple(_require_nonempty_text(item, f"{location}[{index}]") for index, item in enumerate(value))


def parse_spec(raw: Any) -> ExperimentSpec:
    root = _require_dict(raw, "spec")
    _require_exact_keys(root, _TOP_LEVEL_KEYS, "spec")

    schema_version = _require_int(root["schema_version"], "schema_version")
    if schema_version != 1:
        raise ContractError("schema_version must be 1")

    experiment_id = _require_nonempty_text(root["experiment_id"], "experiment_id")
    if not re.fullmatch(r"EXP-\d{4}-[a-z0-9-]+", experiment_id):
        raise ContractError("experiment_id must match EXP-0000-lowercase-slug")

    data = _require_dict(root["data"], "data")
    _require_exact_keys(
        data,
        {"kind", "seed", "samples", "structured_phi", "control_phi", "sigma"},
        "data",
    )
    kind = _require_nonempty_text(data["kind"], "data.kind")
    if kind != "paired_ar1":
        raise ContractError("data.kind must be paired_ar1")
    seed = _require_int(data["seed"], "data.seed")
    samples = _require_int(data["samples"], "data.samples")
    structured_phi = _require_number(data["structured_phi"], "data.structured_phi")
    control_phi = _require_number(data["control_phi"], "data.control_phi")
    sigma = _require_number(data["sigma"], "data.sigma")
    if seed < 0:
        raise ContractError("data.seed must be non-negative")
    if samples < 100:
        raise ContractError("data.samples must be at least 100")
    if abs(structured_phi) >= 1 or abs(control_phi) >= 1:
        raise ContractError("AR(1) coefficients must be strictly between -1 and 1")
    if structured_phi == control_phi:
        raise ContractError("structured_phi and control_phi must differ")
    if sigma <= 0:
        raise ContractError("data.sigma must be positive")

    method = _require_dict(root["method"], "method")
    _require_exact_keys(
        method,
        {"strategy", "signal_lag", "train_fraction", "cost_bps", "annualization_periods", "trial_count"},
        "method",
    )
    strategy = _require_nonempty_text(method["strategy"], "method.strategy")
    signal_lag = _require_int(method["signal_lag"], "method.signal_lag")
    train_fraction = _require_number(method["train_fraction"], "method.train_fraction")
    cost_bps = _require_number(method["cost_bps"], "method.cost_bps")
    annualization_periods = _require_int(method["annualization_periods"], "method.annualization_periods")
    trial_count = _require_int(method["trial_count"], "method.trial_count")
    if strategy != "lagged_sign_reversal" or signal_lag != 1:
        raise ContractError("the version 1 runner only permits lagged_sign_reversal with signal_lag=1")
    if not 0.5 <= train_fraction <= 0.9:
        raise ContractError("method.train_fraction must be between 0.5 and 0.9")
    if cost_bps < 0:
        raise ContractError("method.cost_bps must be non-negative")
    if annualization_periods <= 0:
        raise ContractError("method.annualization_periods must be positive")
    if trial_count != 1:
        raise ContractError("version 1 requires a single preregistered trial")

    decision = _require_dict(root["decision_rule"], "decision_rule")
    _require_exact_keys(
        decision,
        {"min_structured_oos_cumulative_return", "require_structured_oos_mean_above_control"},
        "decision_rule",
    )
    minimum_return = _require_number(
        decision["min_structured_oos_cumulative_return"],
        "decision_rule.min_structured_oos_cumulative_return",
    )
    require_above_control = decision["require_structured_oos_mean_above_control"]
    if not isinstance(require_above_control, bool):
        raise ContractError("decision_rule.require_structured_oos_mean_above_control must be boolean")

    capital_authorized = root["capital_authorized"]
    if capital_authorized is not False:
        raise ContractError("research specifications must set capital_authorized to false")

    return ExperimentSpec(
        schema_version=schema_version,
        experiment_id=experiment_id,
        title=_require_nonempty_text(root["title"], "title"),
        hypothesis=_require_nonempty_text(root["hypothesis"], "hypothesis"),
        data=DataSpec(kind, seed, samples, structured_phi, control_phi, sigma),
        method=MethodSpec(
            strategy,
            signal_lag,
            train_fraction,
            cost_bps,
            annualization_periods,
            trial_count,
        ),
        decision_rule=DecisionRule(minimum_return, require_above_control),
        bias_controls=_require_text_list(root["bias_controls"], "bias_controls"),
        failure_modes=_require_text_list(root["failure_modes"], "failure_modes"),
        confidence=_require_nonempty_text(root["confidence"], "confidence"),
        capital_authorized=capital_authorized,
        next_experiment=_require_nonempty_text(root["next_experiment"], "next_experiment"),
    )


def load_spec(path: Path) -> ExperimentSpec:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid JSON in {path}: {exc}") from exc
    return parse_spec(raw)
