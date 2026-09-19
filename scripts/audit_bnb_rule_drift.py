"""Capture declared resolution rules for historical public BNB five-minute markets."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from aoae.experiment import write_record


def fetch(identifier: dict) -> tuple[dict, dict]:
    query = {"slug": identifier["slug"]} if "condition_id" not in identifier else {"condition_ids": identifier["condition_id"]}
    url = "https://gamma-api.polymarket.com/markets?" + urlencode(query)
    request = Request(url, headers={"User-Agent": "AOAE/0.1 read-only-research"})
    with urlopen(request, timeout=60) as response:
        body = response.read()
        metadata = {"http_date": response.headers.get("Date"), "sha256": hashlib.sha256(body).hexdigest(), "byte_count": len(body)}
    rows = json.loads(body)
    if not isinstance(rows, list) or len(rows) != 1:
        raise RuntimeError(f"expected exactly one market for {query}, received {len(rows) if isinstance(rows, list) else 'non-list'}")
    return rows[0], metadata


def classify(text: str) -> str:
    lowered = text.lower()
    if "twap-60s" in lowered:
        return "twap_60_seconds"
    if "twap-30s" in lowered:
        return "twap_30_seconds"
    if "bnb-usd" in lowered and "twap" not in lowered:
        return "start_end_stream_price"
    return "unknown"


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: audit_bnb_rule_drift.py SPEC OUTPUT")
    spec_path, output = map(Path, sys.argv[1:])
    spec = json.loads(spec_path.read_bytes())
    if any(spec.get(key) is not False for key in ("orders_authorized", "authentication_authorized", "capital_authorized")):
        raise ValueError("audit requires zero orders, zero authentication, and zero capital")
    observations = []
    for declared in spec["markets"]:
        market, capture = fetch(declared)
        text = "\n".join(str(market.get(key) or "") for key in ("description", "resolutionSource"))
        observations.append({
            **declared,
            "returned_slug": market.get("slug"),
            "question": market.get("question"),
            "resolution_source": market.get("resolutionSource"),
            "rule_class": classify(text),
            "description": market.get("description"),
            "capture": capture,
        })
    classes = [item["rule_class"] for item in observations]
    record = {
        "schema_version": 1,
        "record_type": "public_bnb_five_minute_rule_drift_audit",
        "captured_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "observations": observations,
        "result": {
            "rule_drift_confirmed": len(set(classes)) > 1 and "unknown" not in classes,
            "sequence": classes,
            "historical_wallet_mechanism_transferable_without_retest": False,
        },
        "orders_placed": 0,
        "authentication_used": False,
        "capital_authorized": False,
        "decision": "retest_current_rule_only",
    }
    write_record(output, record)
    print(json.dumps(record["result"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
