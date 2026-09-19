"""Preregistered one-step Treasury slope-change hypothesis."""

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
from aoae.real_hypothesis import pearson_correlation


@dataclass(frozen=True)
class SlopeReversalSpec:
    hypothesis_id: str
    hypothesis: str
    source_url: str
    local_path: str
    period_start: date
    period_end: date
    minimum_rows: int
    maximum_rows: int
    minimum_lag_pairs: int
    maximum_lag1_correlation: float
    benchmark_correlation: float
    bias_controls: tuple[str, ...]
    failure_modes: tuple[str, ...]
    confidence: str
    next_experiment: str
    capital_authorized: bool = False
    strategy_mining_authorized: bool = False


def _object(value: Any, keys: set[str], location: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
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
        raise ContractError(f"{location} must be numeric")
    return float(value)


def _texts(value: Any, location: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ContractError(f"{location} must be a non-empty list")
    return tuple(_text(item, f"{location}[{index}]") for index, item in enumerate(value))


def load_slope_reversal_spec(path: Path) -> SlopeReversalSpec:
    root = _object(json.loads(path.read_text(encoding="utf-8")), {
        "schema_version", "hypothesis_id", "title", "hypothesis", "data", "method",
        "benchmark", "decision_rule", "bias_controls", "failure_modes", "confidence",
        "preregistration_state", "strategy_mining_authorized", "capital_authorized", "next_experiment",
    }, "spec")
    if root["schema_version"] != 1 or root["preregistration_state"] != "locked_before_download":
        raise ContractError("hypothesis must use schema 1 and be locked before download")
    if root["hypothesis_id"] != "HYP-0003-treasury-slope-change-reversal":
        raise ContractError("unexpected hypothesis_id")

    data = _object(root["data"], {
        "source_url", "local_path", "period_start", "period_end", "required_fields",
        "minimum_rows", "maximum_rows", "availability_policy",
    }, "data")
    if data["required_fields"] != ["BC_2YEAR", "BC_10YEAR"]:
        raise ContractError("required fields changed")
    if data["availability_policy"] != "official_archive_snapshot":
        raise ContractError("availability policy changed")
    source_url = _text(data["source_url"], "data.source_url")
    local_path = _text(data["local_path"], "data.local_path")
    if not source_url.startswith("https://home.treasury.gov/"):
        raise ContractError("source must be the official Treasury site")
    if Path(local_path).is_absolute() or not local_path.startswith("data/raw/"):
        raise ContractError("local path must remain under data/raw")
    period_start = date.fromisoformat(data["period_start"])
    period_end = date.fromisoformat(data["period_end"])
    minimum_rows = _integer(data["minimum_rows"], "data.minimum_rows")
    maximum_rows = _integer(data["maximum_rows"], "data.maximum_rows")
    if period_end < period_start or not 0 < minimum_rows <= maximum_rows:
        raise ContractError("data date or row bounds are invalid")

    method = _object(root["method"], {
        "transformation", "predictor_lag_observations", "metric", "imputation",
        "trial_count", "trading_costs",
    }, "method")
    if method != {
        "transformation": "lag1_of_consecutive_observation_2s10s_spread_change_basis_points",
        "predictor_lag_observations": 1,
        "metric": "pearson_correlation",
        "imputation": "none",
        "trial_count": 1,
        "trading_costs": "not_applicable_no_trading",
    }:
        raise ContractError("version 1 method is fixed and permits one non-trading trial")

    benchmark = _object(root["benchmark"], {"description", "lag1_correlation"}, "benchmark")
    decision = _object(root["decision_rule"], {"minimum_lag_pairs", "maximum_lag1_correlation"}, "decision_rule")
    benchmark_correlation = _number(benchmark["lag1_correlation"], "benchmark.lag1_correlation")
    maximum_correlation = _number(decision["maximum_lag1_correlation"], "decision_rule.maximum_lag1_correlation")
    minimum_lag_pairs = _integer(decision["minimum_lag_pairs"], "decision_rule.minimum_lag_pairs")
    if benchmark_correlation != 0 or not -1 <= maximum_correlation < benchmark_correlation:
        raise ContractError("benchmark or decision correlation is invalid")
    if minimum_lag_pairs < 200 or minimum_rows < minimum_lag_pairs + 2:
        raise ContractError("insufficient preregistered sample size")
    if root["strategy_mining_authorized"] is not False or root["capital_authorized"] is not False:
        raise ContractError("hypothesis cannot authorize strategy mining or capital")

    return SlopeReversalSpec(
        hypothesis_id=root["hypothesis_id"],
        hypothesis=_text(root["hypothesis"], "hypothesis"),
        source_url=source_url,
        local_path=local_path,
        period_start=period_start,
        period_end=period_end,
        minimum_rows=minimum_rows,
        maximum_rows=maximum_rows,
        minimum_lag_pairs=minimum_lag_pairs,
        maximum_lag1_correlation=maximum_correlation,
        benchmark_correlation=benchmark_correlation,
        bias_controls=_texts(root["bias_controls"], "bias_controls"),
        failure_modes=_texts(root["failure_modes"], "failure_modes"),
        confidence=_text(root["confidence"], "confidence"),
        next_experiment=_text(root["next_experiment"], "next_experiment"),
    )


def evaluate_slope_reversal(xml_bytes: bytes, spec: SlopeReversalSpec, preregistration_commit: str) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{7,40}", preregistration_commit):
        raise ContractError("preregistration_commit must be a Git commit hash")
    root = ET.fromstring(xml_bytes)
    namespace = {"m": "http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"}
    rows: list[tuple[date, Decimal, Decimal]] = []
    missing = 0
    for item in root.findall(".//m:properties", namespace):
        values = {child.tag.rsplit("}", 1)[-1]: child.text for child in item}
        if not values.get("NEW_DATE"):
            continue
        if not values.get("BC_2YEAR") or not values.get("BC_10YEAR"):
            missing += 1
            continue
        rows.append((
            datetime.fromisoformat(values["NEW_DATE"]).date(),
            Decimal(values["BC_2YEAR"]),
            Decimal(values["BC_10YEAR"]),
        ))
    if len(rows) < 3:
        raise ContractError("holdout contains too few complete observations")

    dates = [row[0] for row in rows]
    spreads = [(two_year - ten_year) * 100 for _, two_year, ten_year in rows]
    changes = [float(current - previous) for previous, current in zip(spreads, spreads[1:])]
    predictors = changes[:-1]
    outcomes = changes[1:]
    correlation = round(pearson_correlation(predictors, outcomes), 12)
    quality_checks = {
        "row_count_within_bounds": spec.minimum_rows <= len(rows) <= spec.maximum_rows,
        "required_fields_complete": missing == 0,
        "dates_unique_and_increasing": dates == sorted(set(dates)),
        "dates_within_holdout": all(spec.period_start <= value <= spec.period_end for value in dates),
    }
    sample_check = len(predictors) >= spec.minimum_lag_pairs
    correlation_check = correlation <= spec.maximum_lag1_correlation
    passed = all(quality_checks.values()) and sample_check and correlation_check
    nonzero_direction_pairs = sum(left * right != 0 for left, right in zip(predictors, outcomes, strict=True))
    opposite_direction_pairs = sum(left * right < 0 for left, right in zip(predictors, outcomes, strict=True))
    return {
        "schema_version": 1,
        "hypothesis_id": spec.hypothesis_id,
        "record_type": "preregistered_real_data_temporal_structure_test",
        "preregistration_commit": preregistration_commit,
        "hypothesis": spec.hypothesis,
        "data": {
            "source_url": spec.source_url,
            "snapshot_sha256": hashlib.sha256(xml_bytes).hexdigest(),
            "snapshot_bytes": len(xml_bytes),
            "first_date": dates[0].isoformat(),
            "last_date": dates[-1].isoformat(),
            "rows": len(rows),
            "missing_required_rows": missing,
        },
        "method": {
            "transformation": "lag1_of_consecutive_observation_2s10s_spread_change_basis_points",
            "predictor_lag_observations": 1,
            "metric": "pearson_correlation",
            "benchmark_correlation": spec.benchmark_correlation,
            "maximum_lag1_correlation": spec.maximum_lag1_correlation,
            "minimum_lag_pairs": spec.minimum_lag_pairs,
            "lag_pairs": len(predictors),
            "trial_count": 1,
            "imputation": "none",
            "trading_costs": "not_applicable_no_trading",
            "bias_controls": list(spec.bias_controls),
        },
        "evidence": {
            "lag1_pearson_correlation": correlation,
            "mean_spread_change_bps": round(math.fsum(changes) / len(changes), 12),
            "opposite_nonzero_direction_rate": (
                round(opposite_direction_pairs / nonzero_direction_pairs, 12)
                if nonzero_direction_pairs else 0.0
            ),
        },
        "result": {
            "status": "PASS" if passed else "FAIL",
            "checks": {
                **quality_checks,
                "minimum_lag_pairs_met": sample_check,
                "maximum_lag1_correlation_met": correlation_check,
            },
            "interpretation": (
                "The untouched holdout supports the preregistered one-observation slope-change reversal threshold. This is weak temporal structure, not tradable alpha."
                if passed else "The untouched holdout falsified or could not evaluate the preregistered one-observation slope-change reversal hypothesis."
            ),
        },
        "failure_modes": list(spec.failure_modes),
        "confidence": spec.confidence,
        "decision": "temporal_structure_supported" if passed else "temporal_structure_not_supported",
        "strategy_mining_authorized": False,
        "capital_authorized": False,
        "next_experiment": spec.next_experiment,
    }


def run_slope_reversal_file(spec_path: Path, repo_root: Path, preregistration_commit: str) -> dict[str, Any]:
    spec = load_slope_reversal_spec(spec_path)
    data_path = (repo_root / spec.local_path).resolve()
    raw_root = (repo_root / "data" / "raw").resolve()
    if raw_root not in data_path.parents:
        raise ContractError("holdout data must remain in data/raw")
    return evaluate_slope_reversal(data_path.read_bytes(), spec, preregistration_commit)
