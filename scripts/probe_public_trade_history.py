"""Read-only public trade-history probe for hypothetical maker fill evidence."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from aoae.experiment import write_record


def fetch_sells(condition_id: str, limit: int) -> tuple[list[dict], dict]:
    query = urlencode({"market": condition_id, "side": "SELL", "takerOnly": "true", "limit": limit})
    request = Request("https://data-api.polymarket.com/trades?" + query, headers={"User-Agent": "AOAE/0.1 read-only-research"})
    with urlopen(request, timeout=30) as response:
        body = response.read()
        metadata = {
            "http_date": response.headers.get("Date"),
            "sha256": hashlib.sha256(body).hexdigest(),
            "byte_count": len(body),
        }
    document = json.loads(body)
    if not isinstance(document, list):
        raise ValueError("public trades response must be a list")
    return document, metadata


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit("usage: probe_public_trade_history.py SPEC FILL_RESULT OUTPUT")
    spec_path, fill_path, output = map(Path, sys.argv[1:])
    spec = json.loads(spec_path.read_bytes())
    fill = json.loads(fill_path.read_bytes())
    if spec.get("orders_authorized") is not False or spec.get("capital_authorized") is not False:
        raise ValueError("trade-history probe requires zero orders and zero capital")
    paper_bids = {leg["name"]: float(leg["paper_bid"]) for leg in fill["legs"]}
    after = int(datetime.fromisoformat(spec["after_utc"].replace("Z", "+00:00")).timestamp())
    legs = []
    captures = []
    for declared in spec["legs"]:
        trades, capture = fetch_sells(declared["condition_id"], int(spec["per_market_limit"]))
        captures.append({"name": declared["name"], **capture})
        bid = paper_bids[declared["name"]]
        eligible = [
            trade for trade in trades
            if str(trade.get("asset")) == declared["token"]
            and trade.get("side") == "SELL"
            and int(trade["timestamp"]) >= after
            and float(trade["price"]) <= bid
        ]
        timestamps = [int(trade["timestamp"]) for trade in eligible]
        legs.append({
            "name": declared["name"],
            "paper_bid": bid,
            "sell_trades_at_or_below_bid": len(eligible),
            "sell_volume_at_or_below_bid": round(sum(float(trade["size"]) for trade in eligible), 8),
            "first_evidence_utc": datetime.fromtimestamp(min(timestamps), tz=timezone.utc).isoformat().replace("+00:00", "Z") if timestamps else None,
            "last_evidence_utc": datetime.fromtimestamp(max(timestamps), tz=timezone.utc).isoformat().replace("+00:00", "Z") if timestamps else None,
        })
    evidenced = sum(leg["sell_trades_at_or_below_bid"] > 0 for leg in legs)
    record = {
        "schema_version": 1,
        "record_type": "public_taker_sell_history_fill_evidence",
        "captured_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "method": {
            "after_utc": spec["after_utc"],
            "per_market_limit": spec["per_market_limit"],
            "endpoint": "https://data-api.polymarket.com/trades",
            "taker_only": True,
            "side": "SELL",
            "orders_placed": 0,
            "authentication_used": False,
        },
        "captures": captures,
        "legs": legs,
        "result": {
            "legs_with_historical_fill_evidence": evidenced,
            "all_legs_with_historical_fill_evidence": evidenced == len(legs),
            "interpretation": "Historical taker sells at or below the paper bid show price-level activity, not queue position or a simultaneous complete-set fill.",
        },
        "capital_authorized": False,
        "decision": "continue_forward_queue_study" if evidenced == len(legs) else "reject_or_reprice_inactive_legs",
    }
    write_record(output, record)
    print(json.dumps(record["result"] | {"legs": legs}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
