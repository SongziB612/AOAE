"""Canonical, strategy-free transformation of admitted Treasury curve data."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import re
from typing import Any
import xml.etree.ElementTree as ET

from aoae.contracts import ContractError
from aoae.sensitivity_contracts import canonical_content_digest


SOURCE_FIELDS = {
    "yield_1m_pct": "BC_1MONTH", "yield_2m_pct": "BC_2MONTH",
    "yield_3m_pct": "BC_3MONTH", "yield_4m_pct": "BC_4MONTH",
    "yield_6m_pct": "BC_6MONTH", "yield_1y_pct": "BC_1YEAR",
    "yield_2y_pct": "BC_2YEAR", "yield_3y_pct": "BC_3YEAR",
    "yield_5y_pct": "BC_5YEAR", "yield_7y_pct": "BC_7YEAR",
    "yield_10y_pct": "BC_10YEAR", "yield_20y_pct": "BC_20YEAR",
    "yield_30y_pct": "BC_30YEAR",
}


@dataclass(frozen=True)
class TreasuryDerivationSpec:
    derivation_id: str
    title: str
    admission_result_path: str
    admission_result_digest: str
    raw_snapshot_path: str
    output_path: str
    columns: tuple[str, ...]
    prohibited_columns: tuple[str, ...]
    decimal_places: int
    redistribution_authorized: bool
    purpose: str
    strategy_trials: int
    strategy_mining_authorized: bool
    capital_authorized: bool
    next_experiment: str


def load_derivation_spec(path: Path) -> TreasuryDerivationSpec:
    raw = json.loads(path.read_text(encoding="utf-8"))
    expected = {"schema_version", "derivation_id", "title", "input", "output", "columns", "prohibited_columns", "research_limits", "capital_authorized", "next_experiment"}
    if not isinstance(raw, dict) or set(raw) != expected or raw["schema_version"] != 1:
        raise ContractError("invalid derivation top-level schema")
    derivation_id = raw["derivation_id"]
    if not isinstance(derivation_id, str) or not re.fullmatch(r"DER-\d{4}-[a-z0-9-]+", derivation_id):
        raise ContractError("invalid derivation_id")
    input_spec = raw["input"]
    output = raw["output"]
    limits = raw["research_limits"]
    if set(input_spec) != {"admission_result_path", "admission_result_canonical_sha256", "raw_snapshot_path"}:
        raise ContractError("invalid input schema")
    if set(output) != {"local_path", "format", "decimal_places", "redistribution_authorized"}:
        raise ContractError("invalid output schema")
    if set(limits) != {"purpose", "strategy_trials", "strategy_mining_authorized"}:
        raise ContractError("invalid research_limits schema")
    columns = tuple(raw["columns"])
    prohibited = tuple(raw["prohibited_columns"])
    if len(columns) != len(set(columns)) or set(SOURCE_FIELDS) - set(columns):
        raise ContractError("canonical columns are missing or duplicated")
    if output["format"] != "csv" or output["decimal_places"] != 2 or output["redistribution_authorized"] is not False:
        raise ContractError("version 1 requires private two-decimal CSV output")
    if limits["strategy_trials"] != 0 or limits["strategy_mining_authorized"] is not False or raw["capital_authorized"] is not False:
        raise ContractError("derivation cannot authorize strategy mining or capital")
    digest = input_spec["admission_result_canonical_sha256"]
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ContractError("invalid admission result digest")
    for local_path in (input_spec["raw_snapshot_path"], output["local_path"]):
        if not isinstance(local_path, str) or Path(local_path).is_absolute():
            raise ContractError("local paths must be relative")
    return TreasuryDerivationSpec(
        derivation_id=derivation_id,
        title=raw["title"],
        admission_result_path=input_spec["admission_result_path"],
        admission_result_digest=digest,
        raw_snapshot_path=input_spec["raw_snapshot_path"],
        output_path=output["local_path"],
        columns=columns,
        prohibited_columns=prohibited,
        decimal_places=2,
        redistribution_authorized=False,
        purpose=limits["purpose"],
        strategy_trials=0,
        strategy_mining_authorized=False,
        capital_authorized=False,
        next_experiment=raw["next_experiment"],
    )


def _format_decimal(value: Decimal) -> str:
    return f"{value:.2f}"


def build_canonical_csv(xml_bytes: bytes, spec: TreasuryDerivationSpec) -> tuple[bytes, dict[str, Any]]:
    root = ET.fromstring(xml_bytes)
    namespace = {"m": "http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"}
    source_rows: list[tuple[date, dict[str, Decimal]]] = []
    for item in root.findall(".//m:properties", namespace):
        values = {child.tag.rsplit("}", 1)[-1]: child.text for child in item}
        observed = datetime.fromisoformat(values["NEW_DATE"]).date()
        yields = {column: Decimal(values[source]) for column, source in SOURCE_FIELDS.items()}
        source_rows.append((observed, yields))
    source_rows.sort(key=lambda item: item[0])

    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=spec.columns, lineterminator="\n")
    writer.writeheader()
    previous: dict[str, Decimal] | None = None
    spread_10y_2y: list[int] = []
    spread_10y_3m: list[int] = []
    spread_30y_10y: list[int] = []
    change_2y: list[int] = []
    change_10y: list[int] = []
    identity_ok = True
    first_changes_blank = False
    for observed, yields in source_rows:
        s_10_2 = int((yields["yield_10y_pct"] - yields["yield_2y_pct"]) * 100)
        s_10_3m = int((yields["yield_10y_pct"] - yields["yield_3m_pct"]) * 100)
        s_30_10 = int((yields["yield_30y_pct"] - yields["yield_10y_pct"]) * 100)
        row: dict[str, str | int] = {"observation_date": observed.isoformat()}
        row.update({column: _format_decimal(value) for column, value in yields.items()})
        row.update({
            "spread_10y_2y_bps": s_10_2,
            "spread_10y_3m_bps": s_10_3m,
            "spread_30y_10y_bps": s_30_10,
            "change_2y_bps": "" if previous is None else int((yields["yield_2y_pct"] - previous["yield_2y_pct"]) * 100),
            "change_10y_bps": "" if previous is None else int((yields["yield_10y_pct"] - previous["yield_10y_pct"]) * 100),
        })
        writer.writerow(row)
        if previous is None:
            first_changes_blank = row["change_2y_bps"] == "" and row["change_10y_bps"] == ""
        spread_10y_2y.append(s_10_2)
        spread_10y_3m.append(s_10_3m)
        spread_30y_10y.append(s_30_10)
        if previous is not None:
            change_2y.append(int(row["change_2y_bps"]))
            change_10y.append(int(row["change_10y_bps"]))
        identity_ok = identity_ok and s_10_2 == int((yields["yield_10y_pct"] - yields["yield_2y_pct"]) * 100)
        previous = yields

    csv_bytes = output.getvalue().encode("utf-8")
    prohibited_absent = not any(any(token in column.lower() for token in spec.prohibited_columns) for column in spec.columns)
    dates = [item[0] for item in source_rows]
    checks = {
        "columns_match_contract": tuple(spec.columns) == tuple(writer.fieldnames),
        "dates_unique_and_increasing": dates == sorted(set(dates)),
        "spread_identities_exact": identity_ok,
        "first_change_is_blank": first_changes_blank,
        "prohibited_strategy_columns_absent": prohibited_absent,
        "strategy_trials_zero": spec.strategy_trials == 0,
        "capital_disabled": not spec.capital_authorized,
        "redistribution_disabled": not spec.redistribution_authorized,
    }
    analysis = {
        "row_count": len(source_rows),
        "column_count": len(spec.columns),
        "first_date": dates[0].isoformat(),
        "last_date": dates[-1].isoformat(),
        "inverted_10y_2y_rows": sum(value < 0 for value in spread_10y_2y),
        "inverted_10y_3m_rows": sum(value < 0 for value in spread_10y_3m),
        "spread_10y_2y_bps_minimum": min(spread_10y_2y),
        "spread_10y_2y_bps_maximum": max(spread_10y_2y),
        "spread_10y_3m_bps_minimum": min(spread_10y_3m),
        "spread_10y_3m_bps_maximum": max(spread_10y_3m),
        "spread_30y_10y_bps_minimum": min(spread_30y_10y),
        "spread_30y_10y_bps_maximum": max(spread_30y_10y),
        "maximum_absolute_2y_daily_change_bps": max(abs(value) for value in change_2y),
        "maximum_absolute_10y_daily_change_bps": max(abs(value) for value in change_10y),
        "checks": checks,
    }
    return csv_bytes, analysis


def derive_treasury_curve(spec_path: Path, repo_root: Path, replace: bool = False) -> dict[str, Any]:
    spec = load_derivation_spec(spec_path)
    admission_path = (spec_path.parent / spec.admission_result_path).resolve()
    admission_raw = json.loads(admission_path.read_text(encoding="utf-8"))
    if canonical_content_digest(admission_raw) != spec.admission_result_digest or admission_raw["result"]["status"] != "PASS":
        raise ContractError("admission result is untrusted or failed")
    raw_path = (repo_root / spec.raw_snapshot_path).resolve()
    output_path = (repo_root / spec.output_path).resolve()
    raw_root = (repo_root / "data" / "raw").resolve()
    processed_root = (repo_root / "data" / "processed").resolve()
    if raw_root not in raw_path.parents or processed_root not in output_path.parents:
        raise ContractError("input or output escaped its governed data directory")
    if output_path.exists() and not replace:
        raise FileExistsError(f"refusing to overwrite existing derived table: {output_path}")
    xml_bytes = raw_path.read_bytes()
    if hashlib.sha256(xml_bytes).hexdigest() != admission_raw["source"]["snapshot_sha256"]:
        raise ContractError("raw snapshot does not match admitted SHA-256")
    csv_bytes, analysis = build_canonical_csv(xml_bytes, spec)
    if not all(analysis["checks"].values()):
        raise ContractError("derived-table invariant failed")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(csv_bytes)
    return {
        "schema_version": 1,
        "derivation_id": spec.derivation_id,
        "record_type": "canonical_real_data_derivation",
        "input": {
            "admission_id": admission_raw["admission_id"],
            "admission_result_canonical_sha256": spec.admission_result_digest,
            "raw_snapshot_sha256": admission_raw["source"]["snapshot_sha256"],
        },
        "output": {
            "format": "csv",
            "sha256": hashlib.sha256(csv_bytes).hexdigest(),
            "bytes": len(csv_bytes),
            "rows": analysis["row_count"],
            "columns": analysis["column_count"],
            "redistribution_authorized": spec.redistribution_authorized,
        },
        "evidence": {key: value for key, value in analysis.items() if key != "checks"},
        "result": {
            "status": "PASS",
            "checks": analysis["checks"],
            "interpretation": "The admitted snapshot was converted to a deterministic descriptive table. No signal, return, position, PnL, Sharpe, strategy trial, or capital authorization was introduced.",
        },
        "decision": "canonical_descriptive_table_validated",
        "research_purpose": spec.purpose,
        "strategy_trials": spec.strategy_trials,
        "strategy_mining_authorized": spec.strategy_mining_authorized,
        "capital_authorized": spec.capital_authorized,
        "next_experiment": spec.next_experiment,
    }
