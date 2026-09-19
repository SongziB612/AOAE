"""Strict metadata admission and quality audit for the first real dataset."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any
import xml.etree.ElementTree as ET

from aoae.contracts import ContractError


@dataclass(frozen=True)
class DataAdmissionSpec:
    admission_id: str
    title: str
    provider: str
    dataset: str
    source_url: str
    documentation_url: str
    local_path: str
    period_start: date
    period_end: date
    required_fields: tuple[str, ...]
    minimum_rows: int
    maximum_rows: int
    maximum_missing_fraction: float
    minimum_yield_percent: float
    maximum_yield_percent: float
    weekend_rows_allowed: int
    license_status: str
    raw_redistribution_authorized: bool
    attribution_required: bool
    observation_basis: str
    timezone: str
    research_available: str
    revisions_possible: bool
    purpose: str
    strategy_trials: int
    strategy_mining_authorized: bool
    capital_authorized: bool
    next_experiment: str


def _exact(value: dict[str, Any], expected: set[str], location: str) -> None:
    missing = sorted(expected - value.keys())
    extra = sorted(value.keys() - expected)
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


def load_data_admission_spec(path: Path) -> DataAdmissionSpec:
    raw = json.loads(path.read_text(encoding="utf-8"))
    root = _object(raw, "spec")
    _exact(root, {"schema_version", "admission_id", "title", "source", "snapshot", "temporal", "license", "quality", "research_limits", "capital_authorized", "next_experiment"}, "spec")
    if _integer(root["schema_version"], "schema_version") != 1:
        raise ContractError("schema_version must be 1")
    admission_id = _text(root["admission_id"], "admission_id")
    if not re.fullmatch(r"ADM-\d{4}-[a-z0-9-]+", admission_id):
        raise ContractError("invalid admission_id")

    source = _object(root["source"], "source")
    _exact(source, {"provider", "dataset", "url", "documentation_url", "format", "authentication", "access_cost_usd", "official_source"}, "source")
    if source["official_source"] is not True or source["authentication"] != "none" or _number(source["access_cost_usd"], "source.access_cost_usd") != 0 or source["format"] != "xml":
        raise ContractError("version 1 admits only an official, free, unauthenticated XML source")
    source_url = _text(source["url"], "source.url")
    documentation_url = _text(source["documentation_url"], "source.documentation_url")
    if not source_url.startswith("https://home.treasury.gov/") or not documentation_url.startswith("https://home.treasury.gov/"):
        raise ContractError("source URLs must use the official Treasury HTTPS domain")

    snapshot = _object(root["snapshot"], "snapshot")
    _exact(snapshot, {"period_start", "period_end", "local_path"}, "snapshot")
    period_start = date.fromisoformat(_text(snapshot["period_start"], "snapshot.period_start"))
    period_end = date.fromisoformat(_text(snapshot["period_end"], "snapshot.period_end"))
    local_path = _text(snapshot["local_path"], "snapshot.local_path")
    if Path(local_path).is_absolute() or not local_path.startswith("data/raw/") or period_end < period_start:
        raise ContractError("snapshot path or date range is invalid")

    temporal = _object(root["temporal"], "temporal")
    _exact(temporal, {"observation_basis", "timezone", "research_available", "revisions_possible"}, "temporal")
    if temporal["research_available"] != "next_us_business_day" or temporal["revisions_possible"] is not True:
        raise ContractError("temporal policy must prevent same-day use and acknowledge revisions")

    license_spec = _object(root["license"], "license")
    _exact(license_spec, {"status", "raw_redistribution_authorized", "attribution_required"}, "license")
    if license_spec["raw_redistribution_authorized"] is not False or license_spec["attribution_required"] is not True:
        raise ContractError("raw redistribution must remain disabled and attribution required")

    quality = _object(root["quality"], "quality")
    _exact(quality, {"required_fields", "minimum_rows", "maximum_rows", "maximum_missing_fraction", "minimum_yield_percent", "maximum_yield_percent", "weekend_rows_allowed"}, "quality")
    raw_fields = quality["required_fields"]
    if not isinstance(raw_fields, list) or not raw_fields:
        raise ContractError("quality.required_fields must be a non-empty list")
    fields = tuple(_text(field, "quality.required_fields") for field in raw_fields)
    if len(set(fields)) != len(fields):
        raise ContractError("quality.required_fields must be unique")
    minimum_rows = _integer(quality["minimum_rows"], "quality.minimum_rows")
    maximum_rows = _integer(quality["maximum_rows"], "quality.maximum_rows")
    missing = _number(quality["maximum_missing_fraction"], "quality.maximum_missing_fraction")
    lower = _number(quality["minimum_yield_percent"], "quality.minimum_yield_percent")
    upper = _number(quality["maximum_yield_percent"], "quality.maximum_yield_percent")
    weekend = _integer(quality["weekend_rows_allowed"], "quality.weekend_rows_allowed")
    if not 0 < minimum_rows <= maximum_rows or not 0 <= missing < 1 or lower >= upper or weekend < 0:
        raise ContractError("quality thresholds are invalid")

    limits = _object(root["research_limits"], "research_limits")
    _exact(limits, {"purpose", "strategy_trials", "strategy_mining_authorized"}, "research_limits")
    trials = _integer(limits["strategy_trials"], "research_limits.strategy_trials")
    if trials != 0 or limits["strategy_mining_authorized"] is not False or root["capital_authorized"] is not False:
        raise ContractError("data admission cannot authorize strategy mining or capital")

    return DataAdmissionSpec(
        admission_id=admission_id,
        title=_text(root["title"], "title"),
        provider=_text(source["provider"], "source.provider"),
        dataset=_text(source["dataset"], "source.dataset"),
        source_url=source_url,
        documentation_url=documentation_url,
        local_path=local_path,
        period_start=period_start,
        period_end=period_end,
        required_fields=fields,
        minimum_rows=minimum_rows,
        maximum_rows=maximum_rows,
        maximum_missing_fraction=missing,
        minimum_yield_percent=lower,
        maximum_yield_percent=upper,
        weekend_rows_allowed=weekend,
        license_status=_text(license_spec["status"], "license.status"),
        raw_redistribution_authorized=False,
        attribution_required=True,
        observation_basis=_text(temporal["observation_basis"], "temporal.observation_basis"),
        timezone=_text(temporal["timezone"], "temporal.timezone"),
        research_available=temporal["research_available"],
        revisions_possible=True,
        purpose=_text(limits["purpose"], "research_limits.purpose"),
        strategy_trials=trials,
        strategy_mining_authorized=False,
        capital_authorized=False,
        next_experiment=_text(root["next_experiment"], "next_experiment"),
    )


def audit_treasury_xml(xml_bytes: bytes, spec: DataAdmissionSpec) -> dict[str, Any]:
    root = ET.fromstring(xml_bytes)
    namespaces = {"m": "http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"}
    properties = root.findall(".//m:properties", namespaces)
    rows: list[tuple[date, dict[str, float | None]]] = []
    for item in properties:
        values = {child.tag.rsplit("}", 1)[-1]: child.text for child in item}
        if not values.get("NEW_DATE"):
            continue
        observed = datetime.fromisoformat(values["NEW_DATE"]).date()
        fields: dict[str, float | None] = {}
        for field in spec.required_fields:
            text_value = values.get(field)
            fields[field] = None if text_value in {None, ""} else float(text_value)
        rows.append((observed, fields))

    dates = [item[0] for item in rows]
    duplicate_count = len(dates) - len(set(dates))
    out_of_period = sum(not spec.period_start <= value <= spec.period_end for value in dates)
    weekend_rows = sum(value.weekday() >= 5 for value in dates)
    field_quality: dict[str, dict[str, int | float | None]] = {}
    all_values_in_range = True
    coverage_ok = True
    for field in spec.required_fields:
        present = [row[field] for _, row in rows if row[field] is not None]
        missing_count = len(rows) - len(present)
        missing_fraction = 1.0 if not rows else missing_count / len(rows)
        in_range = all(spec.minimum_yield_percent <= value <= spec.maximum_yield_percent for value in present)
        coverage_ok = coverage_ok and missing_fraction <= spec.maximum_missing_fraction
        all_values_in_range = all_values_in_range and in_range
        field_quality[field] = {
            "missing_count": missing_count,
            "missing_fraction": round(missing_fraction, 12),
            "minimum": None if not present else min(present),
            "maximum": None if not present else max(present),
        }

    checks = {
        "row_count_within_bounds": spec.minimum_rows <= len(rows) <= spec.maximum_rows,
        "dates_unique": duplicate_count == 0,
        "dates_strictly_increasing": dates == sorted(dates) and duplicate_count == 0,
        "dates_within_declared_period": out_of_period == 0,
        "weekend_rows_within_limit": weekend_rows <= spec.weekend_rows_allowed,
        "required_field_coverage": coverage_ok,
        "yield_values_within_bounds": all_values_in_range,
        "strategy_mining_disabled": spec.strategy_trials == 0 and not spec.strategy_mining_authorized,
        "capital_disabled": not spec.capital_authorized,
        "raw_redistribution_disabled": not spec.raw_redistribution_authorized,
    }
    passed = all(checks.values())
    digest = hashlib.sha256(xml_bytes).hexdigest()
    return {
        "schema_version": 1,
        "admission_id": spec.admission_id,
        "record_type": "real_data_quality_admission",
        "source": {
            "provider": spec.provider,
            "dataset": spec.dataset,
            "url": spec.source_url,
            "documentation_url": spec.documentation_url,
            "snapshot_sha256": digest,
            "snapshot_bytes": len(xml_bytes),
        },
        "temporal": {
            "observation_basis": spec.observation_basis,
            "timezone": spec.timezone,
            "research_available": spec.research_available,
            "revisions_possible": spec.revisions_possible,
        },
        "license": {
            "status": spec.license_status,
            "raw_redistribution_authorized": spec.raw_redistribution_authorized,
            "attribution_required": spec.attribution_required,
        },
        "evidence": {
            "row_count": len(rows),
            "first_date": None if not dates else dates[0].isoformat(),
            "last_date": None if not dates else dates[-1].isoformat(),
            "duplicate_date_count": duplicate_count,
            "weekend_row_count": weekend_rows,
            "out_of_period_count": out_of_period,
            "field_quality": field_quality,
        },
        "result": {
            "status": "PASS" if passed else "FAIL",
            "checks": checks,
            "interpretation": "The snapshot is admitted for descriptive data-quality work only; strategy mining, redistribution, and capital remain disabled." if passed else "The snapshot failed its preregistered data-quality admission checks.",
        },
        "decision": "metadata_and_snapshot_quality_admitted" if passed else "data_admission_rejected",
        "research_purpose": spec.purpose,
        "strategy_trials": spec.strategy_trials,
        "strategy_mining_authorized": spec.strategy_mining_authorized,
        "capital_authorized": spec.capital_authorized,
        "next_experiment": spec.next_experiment,
    }


def audit_data_file(spec_path: Path, repo_root: Path) -> dict[str, Any]:
    spec = load_data_admission_spec(spec_path)
    data_path = (repo_root / spec.local_path).resolve()
    raw_root = (repo_root / "data" / "raw").resolve()
    if raw_root not in data_path.parents:
        raise ContractError("data snapshot must remain inside data/raw")
    return audit_treasury_xml(data_path.read_bytes(), spec)
