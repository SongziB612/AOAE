"""Contract and provenance checks for multi-seed sensitivity experiments."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from aoae.contracts import ContractError, ExperimentSpec, load_spec


@dataclass(frozen=True)
class AcceptanceSpec:
    minimum_seed_pass_rate: float
    confidence_level: float
    minimum_wilson_lower_bound: float


@dataclass(frozen=True)
class SensitivitySpec:
    schema_version: int
    experiment_id: str
    title: str
    hypothesis: str
    base_spec_path: str
    base_spec_digest: str
    seeds: tuple[int, ...]
    acceptance: AcceptanceSpec
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
    "base_experiment",
    "seeds",
    "acceptance",
    "bias_controls",
    "failure_modes",
    "confidence",
    "capital_authorized",
    "next_experiment",
}


def canonical_content_digest(raw: Any) -> str:
    payload = json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _exact_keys(value: dict[str, Any], expected: set[str], location: str) -> None:
    missing = sorted(expected - value.keys())
    extra = sorted(value.keys() - expected)
    if missing or extra:
        details = []
        if missing:
            details.append(f"missing={missing}")
        if extra:
            details.append(f"unexpected={extra}")
        raise ContractError(f"{location} has invalid keys: {', '.join(details)}")


def _object(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{location} must be an object")
    return value


def _integer(value: Any, location: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractError(f"{location} must be an integer")
    return value


def _number(value: Any, location: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"{location} must be a number")
    return float(value)


def _text(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{location} must be non-empty text")
    return value.strip()


def _text_list(value: Any, location: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ContractError(f"{location} must be a non-empty list")
    return tuple(_text(item, f"{location}[{index}]") for index, item in enumerate(value))


def parse_sensitivity_spec(raw: Any) -> SensitivitySpec:
    root = _object(raw, "spec")
    _exact_keys(root, _TOP_LEVEL_KEYS, "spec")

    schema_version = _integer(root["schema_version"], "schema_version")
    if schema_version != 1:
        raise ContractError("schema_version must be 1")
    experiment_id = _text(root["experiment_id"], "experiment_id")
    if not re.fullmatch(r"EXP-\d{4}-[a-z0-9-]+", experiment_id):
        raise ContractError("experiment_id must match EXP-0000-lowercase-slug")

    base = _object(root["base_experiment"], "base_experiment")
    _exact_keys(base, {"spec_path", "canonical_sha256"}, "base_experiment")
    base_path = _text(base["spec_path"], "base_experiment.spec_path")
    digest = _text(base["canonical_sha256"], "base_experiment.canonical_sha256")
    if Path(base_path).is_absolute():
        raise ContractError("base_experiment.spec_path must be relative")
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ContractError("base_experiment.canonical_sha256 must be a lowercase SHA-256 digest")

    raw_seeds = root["seeds"]
    if not isinstance(raw_seeds, list):
        raise ContractError("seeds must be a list")
    seeds = tuple(_integer(seed, f"seeds[{index}]") for index, seed in enumerate(raw_seeds))
    if not 20 <= len(seeds) <= 1000:
        raise ContractError("seeds must contain between 20 and 1000 entries")
    if len(set(seeds)) != len(seeds):
        raise ContractError("seeds must not contain duplicates")
    if any(seed < 0 for seed in seeds):
        raise ContractError("seeds must be non-negative")

    acceptance = _object(root["acceptance"], "acceptance")
    _exact_keys(
        acceptance,
        {"minimum_seed_pass_rate", "confidence_level", "minimum_wilson_lower_bound"},
        "acceptance",
    )
    minimum_rate = _number(acceptance["minimum_seed_pass_rate"], "acceptance.minimum_seed_pass_rate")
    confidence_level = _number(acceptance["confidence_level"], "acceptance.confidence_level")
    minimum_lower = _number(
        acceptance["minimum_wilson_lower_bound"],
        "acceptance.minimum_wilson_lower_bound",
    )
    if not 0 < minimum_rate <= 1:
        raise ContractError("minimum_seed_pass_rate must be in (0, 1]")
    if confidence_level != 0.95:
        raise ContractError("version 1 fixes confidence_level at 0.95")
    if not 0 < minimum_lower <= minimum_rate:
        raise ContractError("minimum_wilson_lower_bound must be positive and no greater than pass rate")

    capital_authorized = root["capital_authorized"]
    if capital_authorized is not False:
        raise ContractError("sensitivity research must set capital_authorized to false")

    return SensitivitySpec(
        schema_version=schema_version,
        experiment_id=experiment_id,
        title=_text(root["title"], "title"),
        hypothesis=_text(root["hypothesis"], "hypothesis"),
        base_spec_path=base_path,
        base_spec_digest=digest,
        seeds=seeds,
        acceptance=AcceptanceSpec(minimum_rate, confidence_level, minimum_lower),
        bias_controls=_text_list(root["bias_controls"], "bias_controls"),
        failure_modes=_text_list(root["failure_modes"], "failure_modes"),
        confidence=_text(root["confidence"], "confidence"),
        capital_authorized=capital_authorized,
        next_experiment=_text(root["next_experiment"], "next_experiment"),
    )


def load_sensitivity_spec(path: Path) -> tuple[SensitivitySpec, ExperimentSpec]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid JSON in {path}: {exc}") from exc
    sensitivity = parse_sensitivity_spec(raw)

    experiments_root = path.parent.parent.resolve()
    base_path = (path.parent / sensitivity.base_spec_path).resolve()
    if experiments_root != base_path.parent.parent or experiments_root not in base_path.parents:
        raise ContractError("base experiment must remain inside the experiments directory")
    try:
        base_raw = json.loads(base_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid JSON in base experiment {base_path}: {exc}") from exc
    actual_digest = canonical_content_digest(base_raw)
    if actual_digest != sensitivity.base_spec_digest:
        raise ContractError(
            "base experiment digest mismatch: "
            f"expected={sensitivity.base_spec_digest} actual={actual_digest}"
        )
    return sensitivity, load_spec(base_path)
