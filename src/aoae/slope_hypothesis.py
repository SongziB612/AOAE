"""Preregistered, non-predictive Treasury slope-structure test."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import re
from statistics import median
from typing import Any
import xml.etree.ElementTree as ET

from aoae.contracts import ContractError


@dataclass(frozen=True)
class SlopeStructureSpec:
    hypothesis_id: str
    title: str
    hypothesis: str
    source_url: str
    local_path: str
    period_start: date
    period_end: date
    minimum_rows: int
    maximum_rows: int
    minimum_inversion_rate: float
    benchmark_inversion_rate: float
    bias_controls: tuple[str, ...]
    failure_modes: tuple[str, ...]
    confidence: str
    next_experiment: str
    capital_authorized: bool = False
    strategy_mining_authorized: bool = False


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


def load_slope_structure_spec(path: Path) -> SlopeStructureSpec:
    raw = json.loads(path.read_text(encoding="utf-8"))
    root = _keys(raw, {
        "schema_version", "hypothesis_id", "title", "hypothesis", "data", "method",
        "benchmark", "decision_rule", "bias_controls", "failure_modes", "confidence",
        "preregistration_state", "strategy_mining_authorized", "capital_authorized", "next_experiment",
    }, "spec")
    if root["schema_version"] != 1 or root["preregistration_state"] != "locked_before_download":
        raise ContractError("hypothesis must use schema 1 and be locked before download")
    hypothesis_id = _text(root["hypothesis_id"], "hypothesis_id")
    if hypothesis_id != "HYP-0002-treasury-slope-inversion":
        raise ContractError("unexpected hypothesis_id")

    data = _keys(root["data"], {
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

    method = _keys(root["method"], {"transformation", "metric", "imputation", "trial_count", "trading_costs"}, "method")
    if method != {
        "transformation": "two_year_minus_ten_year_spread_basis_points",
        "metric": "share_of_observations_above_zero",
        "imputation": "none",
        "trial_count": 1,
        "trading_costs": "not_applicable_no_trading",
    }:
        raise ContractError("version 1 method is fixed and permits one non-trading trial")

    benchmark = _keys(root["benchmark"], {"description", "inversion_rate"}, "benchmark")
    decision = _keys(root["decision_rule"], {"minimum_observations", "minimum_inversion_rate"}, "decision_rule")
    benchmark_rate = _number(benchmark["inversion_rate"], "benchmark.inversion_rate")
    minimum_rate = _number(decision["minimum_inversion_rate"], "decision_rule.minimum_inversion_rate")
    minimum_observations = _integer(decision["minimum_observations"], "decision_rule.minimum_observations")
    if benchmark_rate != 0.5 or not benchmark_rate < minimum_rate <= 1:
        raise ContractError("benchmark or inversion threshold is invalid")
    if minimum_observations != minimum_rows:
        raise ContractError("minimum observations must equal the data minimum")
    if root["strategy_mining_authorized"] is not False or root["capital_authorized"] is not False:
        raise ContractError("hypothesis cannot authorize strategy mining or capital")

    return SlopeStructureSpec(
        hypothesis_id=hypothesis_id,
        title=_text(root["title"], "title"),
        hypothesis=_text(root["hypothesis"], "hypothesis"),
        source_url=source_url,
        local_path=local_path,
        period_start=period_start,
        period_end=period_end,
        minimum_rows=minimum_rows,
        maximum_rows=maximum_rows,
        minimum_inversion_rate=minimum_rate,
        benchmark_inversion_rate=benchmark_rate,
        bias_controls=_text_list(root["bias_controls"], "bias_controls"),
        failure_modes=_text_list(root["failure_modes"], "failure_modes"),
        confidence=_text(root["confidence"], "confidence"),
        next_experiment=_text(root["next_experiment"], "next_experiment"),
    )


def evaluate_slope_structure(xml_bytes: bytes, spec: SlopeStructureSpec, preregistration_commit: str) -> dict[str, Any]:
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
            Decimal(values["BC_2YEAR"]),
            Decimal(values["BC_10YEAR"]),
        ))
    if not rows:
        raise ContractError("holdout contains no complete observations")

    dates = [row[0] for row in rows]
    spreads = [float((two_year - ten_year) * 100) for _, two_year, ten_year in rows]
    inversion_count = sum(value > 0 for value in spreads)
    inversion_rate = round(inversion_count / len(spreads), 12)
    quality_checks = {
        "row_count_within_bounds": spec.minimum_rows <= len(rows) <= spec.maximum_rows,
        "required_fields_complete": missing_count == 0,
        "dates_unique_and_increasing": dates == sorted(set(dates)),
        "dates_within_holdout": all(spec.period_start <= value <= spec.period_end for value in dates),
    }
    threshold_check = inversion_rate >= spec.minimum_inversion_rate
    passed = all(quality_checks.values()) and threshold_check
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
            "transformation": "two_year_minus_ten_year_spread_basis_points",
            "metric": "share_of_observations_above_zero",
            "benchmark_inversion_rate": spec.benchmark_inversion_rate,
            "minimum_inversion_rate": spec.minimum_inversion_rate,
            "minimum_observations": spec.minimum_rows,
            "trial_count": 1,
            "imputation": "none",
            "trading_costs": "not_applicable_no_trading",
            "bias_controls": list(spec.bias_controls),
        },
        "evidence": {
            "inversion_count": inversion_count,
            "inversion_rate": inversion_rate,
            "mean_two_year_minus_ten_year_bps": round(math.fsum(spreads) / len(spreads), 12),
            "median_two_year_minus_ten_year_bps": round(median(spreads), 12),
            "minimum_two_year_minus_ten_year_bps": round(min(spreads), 12),
            "maximum_two_year_minus_ten_year_bps": round(max(spreads), 12),
        },
        "result": {
            "status": "PASS" if passed else "FAIL",
            "checks": {
                **quality_checks,
                "minimum_inversion_rate_met": threshold_check,
            },
            "interpretation": (
                "The untouched holdout supports the preregistered persistent-inversion threshold. This describes slope structure, not prediction or alpha."
                if passed else "The untouched holdout falsified or could not evaluate the preregistered persistent-inversion hypothesis."
            ),
        },
        "failure_modes": list(spec.failure_modes),
        "confidence": spec.confidence,
        "decision": "slope_structure_supported" if passed else "slope_structure_not_supported",
        "strategy_mining_authorized": False,
        "capital_authorized": False,
        "next_experiment": spec.next_experiment,
    }


def run_slope_structure_file(spec_path: Path, repo_root: Path, preregistration_commit: str) -> dict[str, Any]:
    spec = load_slope_structure_spec(spec_path)
    data_path = (repo_root / spec.local_path).resolve()
    raw_root = (repo_root / "data" / "raw").resolve()
    if raw_root not in data_path.parents:
        raise ContractError("holdout data must remain in data/raw")
    return evaluate_slope_structure(data_path.read_bytes(), spec, preregistration_commit)
