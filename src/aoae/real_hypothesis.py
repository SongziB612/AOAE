"""Preregistered, non-trading hypothesis test on an untouched Treasury holdout."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any
import xml.etree.ElementTree as ET

from aoae.contracts import ContractError


@dataclass(frozen=True)
class YieldComovementSpec:
    hypothesis_id: str
    title: str
    hypothesis: str
    source_url: str
    local_path: str
    period_start: date
    period_end: date
    minimum_rows: int
    maximum_rows: int
    minimum_paired_changes: int
    minimum_correlation: float
    benchmark_correlation: float
    bias_controls: tuple[str, ...]
    failure_modes: tuple[str, ...]
    confidence: str
    capital_authorized: bool
    strategy_mining_authorized: bool
    next_experiment: str


def _keys(value: Any, expected: set[str], location: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        actual = set(value) if isinstance(value, dict) else type(value).__name__
        raise ContractError(f"{location} schema invalid: {actual}")
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


def _text_list(value: Any, location: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ContractError(f"{location} must be a non-empty list")
    return tuple(_text(item, f"{location}[{index}]") for index, item in enumerate(value))


def load_yield_comovement_spec(path: Path) -> YieldComovementSpec:
    raw = json.loads(path.read_text(encoding="utf-8"))
    root = _keys(raw, {"schema_version", "hypothesis_id", "title", "hypothesis", "data", "method", "benchmark", "decision_rule", "bias_controls", "failure_modes", "confidence", "preregistration_state", "strategy_mining_authorized", "capital_authorized", "next_experiment"}, "spec")
    if root["schema_version"] != 1 or root["preregistration_state"] != "locked_before_download":
        raise ContractError("hypothesis must use schema 1 and be locked before download")
    hypothesis_id = _text(root["hypothesis_id"], "hypothesis_id")
    if not re.fullmatch(r"HYP-\d{4}-[a-z0-9-]+", hypothesis_id):
        raise ContractError("invalid hypothesis_id")

    data = _keys(root["data"], {"source_url", "local_path", "period_start", "period_end", "required_fields", "minimum_rows", "maximum_rows", "availability_policy"}, "data")
    if data["required_fields"] != ["BC_2YEAR", "BC_10YEAR"] or data["availability_policy"] != "next_us_business_day":
        raise ContractError("data fields or availability policy changed")
    source_url = _text(data["source_url"], "data.source_url")
    local_path = _text(data["local_path"], "data.local_path")
    if not source_url.startswith("https://home.treasury.gov/") or Path(local_path).is_absolute() or not local_path.startswith("data/raw/"):
        raise ContractError("source or local path is invalid")
    period_start = date.fromisoformat(data["period_start"])
    period_end = date.fromisoformat(data["period_end"])
    minimum_rows = _integer(data["minimum_rows"], "data.minimum_rows")
    maximum_rows = _integer(data["maximum_rows"], "data.maximum_rows")
    if period_end < period_start or not 0 < minimum_rows <= maximum_rows:
        raise ContractError("data date or row bounds are invalid")

    method = _keys(root["method"], {"transformation", "metric", "imputation", "trial_count", "trading_costs"}, "method")
    if method != {
        "transformation": "consecutive_observation_first_difference_basis_points",
        "metric": "pearson_correlation",
        "imputation": "none",
        "trial_count": 1,
        "trading_costs": "not_applicable_no_trading",
    }:
        raise ContractError("version 1 method is fixed and permits one non-trading trial")
    benchmark = _keys(root["benchmark"], {"description", "pearson_correlation"}, "benchmark")
    decision = _keys(root["decision_rule"], {"minimum_paired_changes", "minimum_pearson_correlation"}, "decision_rule")
    benchmark_correlation = _number(benchmark["pearson_correlation"], "benchmark.pearson_correlation")
    minimum_correlation = _number(decision["minimum_pearson_correlation"], "decision_rule.minimum_pearson_correlation")
    minimum_changes = _integer(decision["minimum_paired_changes"], "decision_rule.minimum_paired_changes")
    if benchmark_correlation != 0 or not 0 < minimum_correlation <= 1 or minimum_changes < 30:
        raise ContractError("benchmark or decision rule is invalid")
    if root["strategy_mining_authorized"] is not False or root["capital_authorized"] is not False:
        raise ContractError("hypothesis cannot authorize strategy mining or capital")

    return YieldComovementSpec(
        hypothesis_id=hypothesis_id,
        title=_text(root["title"], "title"),
        hypothesis=_text(root["hypothesis"], "hypothesis"),
        source_url=source_url,
        local_path=local_path,
        period_start=period_start,
        period_end=period_end,
        minimum_rows=minimum_rows,
        maximum_rows=maximum_rows,
        minimum_paired_changes=minimum_changes,
        minimum_correlation=minimum_correlation,
        benchmark_correlation=benchmark_correlation,
        bias_controls=_text_list(root["bias_controls"], "bias_controls"),
        failure_modes=_text_list(root["failure_modes"], "failure_modes"),
        confidence=_text(root["confidence"], "confidence"),
        capital_authorized=False,
        strategy_mining_authorized=False,
        next_experiment=_text(root["next_experiment"], "next_experiment"),
    )


def pearson_correlation(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or len(left) < 2:
        raise ValueError("Pearson inputs must have equal length of at least two")
    left_mean = math.fsum(left) / len(left)
    right_mean = math.fsum(right) / len(right)
    covariance = math.fsum((x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True))
    left_ss = math.fsum((x - left_mean) ** 2 for x in left)
    right_ss = math.fsum((y - right_mean) ** 2 for y in right)
    if left_ss == 0 or right_ss == 0:
        raise ValueError("Pearson correlation is undefined for a constant series")
    return covariance / math.sqrt(left_ss * right_ss)


def evaluate_yield_comovement(xml_bytes: bytes, spec: YieldComovementSpec, preregistration_commit: str) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{7,40}", preregistration_commit):
        raise ContractError("preregistration_commit must be a Git commit hash")
    root = ET.fromstring(xml_bytes)
    namespace = {"m": "http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"}
    rows: list[tuple[date, Decimal, Decimal]] = []
    missing_count = 0
    for item in root.findall(".//m:properties", namespace):
        values = {child.tag.rsplit("}", 1)[-1]: child.text for child in item}
        if not values.get("NEW_DATE"):
            continue
        if not values.get("BC_2YEAR") or not values.get("BC_10YEAR"):
            missing_count += 1
            continue
        rows.append((
            datetime.fromisoformat(values["NEW_DATE"]).date(),
            Decimal(values["BC_2YEAR"]), Decimal(values["BC_10YEAR"]),
        ))
    dates = [row[0] for row in rows]
    quality_checks = {
        "row_count_within_bounds": spec.minimum_rows <= len(rows) <= spec.maximum_rows,
        "required_fields_complete": missing_count == 0,
        "dates_unique_and_increasing": dates == sorted(set(dates)),
        "dates_within_holdout": all(spec.period_start <= value <= spec.period_end for value in dates),
    }
    changes_2y = [float((current[1] - previous[1]) * 100) for previous, current in zip(rows, rows[1:])]
    changes_10y = [float((current[2] - previous[2]) * 100) for previous, current in zip(rows, rows[1:])]
    correlation = round(pearson_correlation(changes_2y, changes_10y), 12)
    sample_check = len(changes_2y) >= spec.minimum_paired_changes
    correlation_check = correlation >= spec.minimum_correlation
    passed = all(quality_checks.values()) and sample_check and correlation_check
    same_direction_rate = round(sum((x > 0) == (y > 0) for x, y in zip(changes_2y, changes_10y, strict=True)) / len(changes_2y), 12)
    return {
        "schema_version": 1,
        "hypothesis_id": spec.hypothesis_id,
        "record_type": "preregistered_real_data_economic_structure_test",
        "preregistration_commit": preregistration_commit,
        "hypothesis": spec.hypothesis,
        "data": {
            "source_url": spec.source_url,
            "snapshot_sha256": hashlib.sha256(xml_bytes).hexdigest(),
            "snapshot_bytes": len(xml_bytes),
            "first_date": dates[0].isoformat(),
            "last_date": dates[-1].isoformat(),
            "rows": len(rows),
            "missing_required_rows": missing_count,
        },
        "method": {
            "transformation": "consecutive_observation_first_difference_basis_points",
            "metric": "pearson_correlation",
            "benchmark_correlation": spec.benchmark_correlation,
            "minimum_correlation": spec.minimum_correlation,
            "minimum_paired_changes": spec.minimum_paired_changes,
            "paired_changes": len(changes_2y),
            "trial_count": 1,
            "imputation": "none",
            "trading_costs": "not_applicable_no_trading",
            "bias_controls": list(spec.bias_controls),
        },
        "evidence": {
            "pearson_correlation": correlation,
            "same_direction_rate": same_direction_rate,
            "mean_2y_change_bps": round(math.fsum(changes_2y) / len(changes_2y), 12),
            "mean_10y_change_bps": round(math.fsum(changes_10y) / len(changes_10y), 12),
        },
        "result": {
            "status": "PASS" if passed else "FAIL",
            "checks": {
                **quality_checks,
                "minimum_paired_changes_met": sample_check,
                "minimum_correlation_met": correlation_check,
            },
            "interpretation": (
                "The untouched holdout supports the preregistered common-movement threshold. This is economic structure, not predictability or alpha."
                if passed else "The untouched holdout falsified or could not evaluate the preregistered common-movement hypothesis."
            ),
        },
        "failure_modes": list(spec.failure_modes),
        "confidence": spec.confidence,
        "decision": "economic_structure_supported" if passed else "economic_structure_not_supported",
        "strategy_mining_authorized": spec.strategy_mining_authorized,
        "capital_authorized": spec.capital_authorized,
        "next_experiment": spec.next_experiment,
    }


def run_yield_comovement_file(spec_path: Path, repo_root: Path, preregistration_commit: str) -> dict[str, Any]:
    spec = load_yield_comovement_spec(spec_path)
    data_path = (repo_root / spec.local_path).resolve()
    raw_root = (repo_root / "data" / "raw").resolve()
    if raw_root not in data_path.parents:
        raise ContractError("holdout data must remain in data/raw")
    return evaluate_yield_comovement(data_path.read_bytes(), spec, preregistration_commit)
