"""Read-only queue-depth diagnostic for a hypothetical multi-leg maker basket."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from aoae.experiment import write_record


def fetch_book(token: str) -> tuple[dict, dict]:
    request = Request(
        "https://clob.polymarket.com/book?" + urlencode({"token_id": token}),
        headers={"User-Agent": "AOAE/0.1 read-only-research"},
    )
    with urlopen(request, timeout=30) as response:
        body = response.read()
        capture = {
            "http_date": response.headers.get("Date"),
            "sha256": hashlib.sha256(body).hexdigest(),
            "byte_count": len(body),
        }
    return json.loads(body), capture


def main() -> int:
    if len(sys.argv) != 5:
        raise SystemExit("usage: probe_queue_depth.py SPEC FILL_RESULT HISTORY_RESULT OUTPUT")
    spec_path, fill_path, history_path, output = map(Path, sys.argv[1:])
    spec = json.loads(spec_path.read_bytes())
    fill = json.loads(fill_path.read_bytes())
    history = json.loads(history_path.read_bytes())
    if spec.get("orders_authorized") is not False or spec.get("capital_authorized") is not False:
        raise ValueError("queue probe requires zero orders and zero capital")
    bids = {leg["name"]: float(leg["paper_bid"]) for leg in fill["legs"]}
    historical = {leg["name"]: leg for leg in history["legs"]}
    after = datetime.fromisoformat(history["method"]["after_utc"].replace("Z", "+00:00"))
    until = datetime.fromisoformat(history["captured_at_utc"].replace("Z", "+00:00"))
    days = (until - after).total_seconds() / 86400
    legs, captures = [], []
    for declared in spec["legs"]:
        book, capture = fetch_book(declared["token"])
        captures.append({"name": declared["name"], **capture})
        bid = bids[declared["name"]]
        bid_levels = [(float(level["price"]), float(level["size"])) for level in book.get("bids", [])]
        ask_levels = [(float(level["price"]), float(level["size"])) for level in book.get("asks", [])]
        if not bid_levels or not ask_levels:
            raise ValueError("every leg needs a two-sided book")
        queue_ahead = sum(size for price, size in bid_levels if price >= bid)
        daily_flow = float(historical[declared["name"]]["sell_volume_at_or_below_bid"]) / days
        legs.append({
            "name": declared["name"],
            "paper_bid": bid,
            "current_best_bid": max(price for price, _ in bid_levels),
            "current_best_ask": min(price for price, _ in ask_levels),
            "displayed_buy_size_at_or_above_paper_bid": round(queue_ahead, 8),
            "historical_daily_taker_sell_volume_at_or_below_bid": round(daily_flow, 8),
            "optimistic_static_queue_clearance_days": round(queue_ahead / daily_flow, 4) if daily_flow > 0 else None,
        })
    bottleneck = max(
        legs,
        key=lambda leg: (
            float("inf")
            if leg["optimistic_static_queue_clearance_days"] is None
            else leg["optimistic_static_queue_clearance_days"]
        ),
    )
    record = {
        "schema_version": 1,
        "record_type": "public_orderbook_queue_depth_diagnostic",
        "captured_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "method": {
            "historical_days": round(days, 8),
            "queue_assumption": "A new paper buy joins behind all displayed buy size at the same or better price.",
            "clearance_assumption": "Historical taker-sell flow remains constant and is entirely available to clear displayed queue; cancellations, new orders, priority and regime changes are ignored.",
            "orders_placed": 0,
            "authentication_used": False,
        },
        "captures": captures,
        "legs": legs,
        "result": {
            "bottleneck_leg": bottleneck["name"],
            "bottleneck_optimistic_clearance_days": bottleneck["optimistic_static_queue_clearance_days"],
            "interpretation": "This is an optimistic diagnostic, not a fill forecast or guarantee.",
        },
        "capital_authorized": False,
        "decision": "continue_forward_queue_study",
    }
    write_record(output, record)
    print(json.dumps(record["result"] | {"legs": legs}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
