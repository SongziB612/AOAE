"""Independent stdlib-only audit of the admitted prospective event snapshot."""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
from pathlib import Path


root = Path(__file__).parents[1]
directory = root / "research" / "data_admissions" / "0003-polymarket-active-events-retry"
spec = json.loads((directory / "spec.json").read_text(encoding="utf-8"))
result = json.loads((directory / "result.json").read_text(encoding="utf-8"))
raw_path = root / spec["snapshot"]["local_path"]
payload = raw_path.read_bytes()
document = json.loads(payload)
events = document[spec["quality"]["events_key"]]
event_ids = [str(event["id"]) for event in events]
markets = [market for event in events for market in event["markets"]]
market_ids = [str(market["id"]) for market in markets]
captured = datetime.fromisoformat(result["snapshot"]["captured_at_utc"].replace("Z", "+00:00"))
server = parsedate_to_datetime(result["source"]["http_date"]).astimezone(timezone.utc)

checks = {
    "record_passed": result["result"]["status"] == "PASS",
    "source_bound": result["source"]["url"] == spec["source"]["url"],
    "hash_matches": hashlib.sha256(payload).hexdigest() == result["snapshot"]["sha256"],
    "byte_count_matches": len(payload) == result["snapshot"]["bytes"],
    "event_count_matches": len(events) == result["snapshot"]["event_count"],
    "market_count_matches": len(markets) == result["snapshot"]["market_count"],
    "event_ids_unique": len(event_ids) == len(set(event_ids)) and all(event_ids),
    "market_ids_unique": len(market_ids) == len(set(market_ids)) and all(market_ids),
    "events_open": all(event["closed"] is False for event in events),
    "event_fields_present": all(all(field in event for field in spec["quality"]["required_event_fields"]) for event in events),
    "market_fields_present": all(all(field in market for field in spec["quality"]["required_market_fields"]) for market in markets),
    "clock_skew_bounded": abs((captured - server).total_seconds()) <= spec["temporal"]["maximum_server_clock_skew_seconds"],
    "no_auth_or_capital": result["source"]["authentication_used"] is False and result["capital_authorized"] is False,
    "no_trials_or_orders": all(value == 0 for value in result["research_activity"].values()),
}
failed = [name for name, passed in checks.items() if not passed]
if failed:
    raise SystemExit(f"independent_prediction_snapshot_audit=FAIL checks={failed}")
print("independent_prediction_snapshot_audit=PASS")
print(f"sha256={result['snapshot']['sha256']}")
print(f"events={len(events)} markets={len(markets)}")
