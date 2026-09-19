"""Prospective, read-only admission of public event-market metadata."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from aoae.contracts import ContractError


@dataclass(frozen=True)
class PublicEventAdmissionSpec:
    raw: dict[str, Any]
    admission_id: str
    source_url: str
    local_path: str
    maximum_bytes: int
    response_date_required: bool
    events_key: str
    next_cursor_key: str
    minimum_events: int
    maximum_events: int
    required_event_fields: tuple[str, ...]
    required_market_fields: tuple[str, ...]
    maximum_clock_skew_seconds: int


def _exact(value: dict[str, Any], keys: set[str], location: str) -> None:
    missing, extra = keys - value.keys(), value.keys() - keys
    if missing or extra:
        raise ContractError(f"{location} invalid keys: missing={sorted(missing)}, unexpected={sorted(extra)}")


def load_public_event_spec(path: Path) -> PublicEventAdmissionSpec:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ContractError("spec must be an object")
    _exact(raw, {"schema_version", "admission_id", "title", "source", "snapshot", "quality", "temporal", "license", "research_limits", "capital_authorized", "next_experiment"}, "spec")
    source, snapshot, quality, temporal = raw["source"], raw["snapshot"], raw["quality"], raw["temporal"]
    license_terms, limits = raw["license"], raw["research_limits"]
    for name, value in (("source", source), ("snapshot", snapshot), ("quality", quality), ("temporal", temporal), ("license", license_terms), ("research_limits", limits)):
        if not isinstance(value, dict):
            raise ContractError(f"{name} must be an object")
    _exact(source, {"provider", "url", "documentation_url", "format", "authentication", "access_cost_usd", "official_public_endpoint"}, "source")
    _exact(snapshot, {"local_path", "capture_policy", "response_date_header_required", "maximum_bytes"}, "snapshot")
    _exact(quality, {"events_key", "next_cursor_key", "minimum_events", "maximum_events", "required_event_fields", "required_market_fields"}, "quality")
    _exact(temporal, {"capture_clock", "prospective_only", "revisions_possible", "maximum_server_clock_skew_seconds"}, "temporal")
    _exact(license_terms, {"status", "raw_redistribution_authorized", "attribution_required"}, "license")
    _exact(limits, {"purpose", "strategy_trials", "model_trials", "trading_endpoints_authorized", "authenticated_requests_authorized"}, "research_limits")
    url = source["url"]
    parsed = urlparse(url if isinstance(url, str) else "")
    if parsed.scheme != "https" or parsed.hostname != "gamma-api.polymarket.com" or parsed.path != "/events/keyset":
        raise ContractError("source.url must use the locked public Gamma events/keyset HTTPS endpoint")
    locked = (
        raw["schema_version"] == 1
        and isinstance(raw["admission_id"], str)
        and re.fullmatch(r"ADM-\d{4}-polymarket-public-active-events", raw["admission_id"]) is not None
        and source["format"] == "json"
        and source["authentication"] == "none"
        and source["access_cost_usd"] == 0
        and source["official_public_endpoint"] is True
        and snapshot["capture_policy"] == "first_capture_only_after_spec_commit"
        and temporal["capture_clock"] == "UTC"
        and temporal["prospective_only"] is True
        and license_terms["raw_redistribution_authorized"] is False
        and limits["strategy_trials"] == limits["model_trials"] == 0
        and limits["trading_endpoints_authorized"] is False
        and limits["authenticated_requests_authorized"] is False
        and raw["capital_authorized"] is False
    )
    if not locked:
        raise ContractError("public-data, prospective-only, zero-trial, zero-capital safety locks are required")
    ints = (snapshot["maximum_bytes"], quality["minimum_events"], quality["maximum_events"], temporal["maximum_server_clock_skew_seconds"])
    if any(isinstance(x, bool) or not isinstance(x, int) or x <= 0 for x in ints):
        raise ContractError("size, event, and clock limits must be positive integers")
    if quality["minimum_events"] > quality["maximum_events"]:
        raise ContractError("minimum_events cannot exceed maximum_events")
    for field_name in ("required_event_fields", "required_market_fields"):
        fields = quality[field_name]
        if not isinstance(fields, list) or not fields or not all(isinstance(x, str) and x for x in fields):
            raise ContractError(f"quality.{field_name} must be a non-empty text list")
    return PublicEventAdmissionSpec(raw, raw["admission_id"], url, snapshot["local_path"], snapshot["maximum_bytes"], snapshot["response_date_header_required"], quality["events_key"], quality["next_cursor_key"], quality["minimum_events"], quality["maximum_events"], tuple(quality["required_event_fields"]), tuple(quality["required_market_fields"]), temporal["maximum_server_clock_skew_seconds"])


def audit_public_event_payload(payload: bytes, spec: PublicEventAdmissionSpec, captured_at_utc: str, http_date: str | None, preregistration_commit: str) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{7,40}", preregistration_commit):
        raise ContractError("preregistration_commit must be a lowercase Git commit hash")
    try:
        captured = datetime.fromisoformat(captured_at_utc.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError("captured_at_utc must be an ISO-8601 UTC timestamp") from exc
    if captured.utcoffset() != timezone.utc.utcoffset(captured):
        raise ContractError("captured_at_utc must be UTC")
    checks: dict[str, bool] = {"within_byte_limit": len(payload) <= spec.maximum_bytes}
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"response is not valid UTF-8 JSON: {exc}") from exc
    checks["top_level_object"] = isinstance(document, dict)
    events = document.get(spec.events_key, []) if isinstance(document, dict) else []
    checks["events_is_list"] = isinstance(events, list)
    checks["next_cursor_present"] = isinstance(document, dict) and spec.next_cursor_key in document
    if not isinstance(events, list):
        events = []
    checks["event_count_in_range"] = spec.minimum_events <= len(events) <= spec.maximum_events
    event_ids: list[str] = []
    market_ids: list[str] = []
    event_fields_ok = market_fields_ok = active_filter_ok = True
    for event in events:
        if not isinstance(event, dict):
            event_fields_ok = active_filter_ok = False
            continue
        event_fields_ok &= all(field in event for field in spec.required_event_fields)
        event_ids.append(str(event.get("id", "")))
        active_filter_ok &= event.get("closed") is False
        markets = event.get("markets")
        if not isinstance(markets, list) or not markets:
            market_fields_ok = False
            continue
        for market in markets:
            if not isinstance(market, dict):
                market_fields_ok = False
                continue
            market_fields_ok &= all(field in market for field in spec.required_market_fields)
            market_ids.append(str(market.get("id", "")))
    checks.update({
        "required_event_fields_present": bool(event_fields_ok),
        "required_market_fields_present": bool(market_fields_ok),
        "events_are_open": bool(active_filter_ok),
        "event_ids_unique_nonempty": bool(event_ids) and "" not in event_ids and len(event_ids) == len(set(event_ids)),
        "market_ids_unique_nonempty": bool(market_ids) and "" not in market_ids and len(market_ids) == len(set(market_ids)),
    })
    skew: float | None = None
    if http_date:
        try:
            server_time = parsedate_to_datetime(http_date)
            if server_time.tzinfo is None:
                raise ValueError("missing timezone")
            skew = abs((captured - server_time.astimezone(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            skew = None
    checks["server_date_present_and_parseable"] = skew is not None if spec.response_date_required else True
    checks["server_clock_skew_within_limit"] = skew is not None and skew <= spec.maximum_clock_skew_seconds
    passed = all(checks.values())
    return {
        "schema_version": 1,
        "admission_id": spec.admission_id,
        "record_type": "prospective_public_event_snapshot_admission",
        "preregistration_commit": preregistration_commit,
        "source": {"url": spec.source_url, "authentication_used": False, "http_date": http_date},
        "snapshot": {"local_path": spec.local_path, "captured_at_utc": captured_at_utc, "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload), "event_count": len(events), "market_count": len(market_ids), "next_cursor": document.get(spec.next_cursor_key) if isinstance(document, dict) else None},
        "result": {"status": "PASS" if passed else "FAIL", "checks": checks, "interpretation": "The public metadata snapshot passed its preregistered admission checks; it is prospective research evidence, not a profitable strategy." if passed else "The captured response failed one or more preregistered admission checks and is quarantined from modeling."},
        "research_activity": {"strategy_trials": 0, "model_trials": 0, "orders": 0},
        "decision": "admit_for_prospective_observation" if passed else "quarantine_snapshot",
        "capital_authorized": False,
        "next_experiment": spec.raw["next_experiment"],
    }


def capture_public_events(spec_path: Path, repo_root: Path, preregistration_commit: str) -> dict[str, Any]:
    spec = load_public_event_spec(spec_path)
    target = (repo_root.resolve() / spec.local_path).resolve()
    if repo_root.resolve() not in target.parents:
        raise ContractError("snapshot.local_path escapes repo root")
    if target.exists():
        raise FileExistsError(f"refusing to overwrite first prospective snapshot: {target}")
    request = Request(spec.source_url, headers={"User-Agent": "AOAE/0.1 read-only-research"}, method="GET")
    with urlopen(request, timeout=30) as response:
        if response.geturl() != spec.source_url:
            raise ContractError("redirected source URL differs from locked endpoint")
        http_date = response.headers.get("Date")
        payload = response.read(spec.maximum_bytes + 1)
        captured_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as handle:
        handle.write(payload)
    return audit_public_event_payload(payload, spec, captured_at, http_date, preregistration_commit)


def audit_public_events_file(spec_path: Path, repo_root: Path, captured_at_utc: str, http_date: str | None, preregistration_commit: str) -> dict[str, Any]:
    """Audit an already preserved snapshot, including an incomplete capture."""
    spec = load_public_event_spec(spec_path)
    target = (repo_root.resolve() / spec.local_path).resolve()
    if repo_root.resolve() not in target.parents:
        raise ContractError("snapshot.local_path escapes repo root")
    return audit_public_event_payload(target.read_bytes(), spec, captured_at_utc, http_date, preregistration_commit)
