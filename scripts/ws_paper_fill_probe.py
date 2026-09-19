"""Aggressive paper-fill observation over Polymarket's public market WebSocket."""

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from websockets.asyncio.client import connect

from aoae.experiment import write_record
from aoae.paper_fill import apply_market_message, summarize_leg_risk


WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"


async def run(snapshot: Path, slug: str, seconds: float, output: Path) -> None:
    document = json.loads(snapshot.read_bytes())
    legs = {}
    if isinstance(document, dict) and "portfolio_id" in document:
        if document.get("orders_authorized") is not False or document.get("capital_authorized") is not False or document.get("minimum_terminal_payoff_per_set", 0) < 1:
            raise ValueError("portfolio must lock zero orders, zero capital, and payoff floor >= 1")
        event = {"title": document["title"], "slug": document["portfolio_id"]}
        for item in document["legs"]:
            legs[item["token"]] = {"name": item["name"], "tick": float(item["tick"]), "paper_bid": None, "cross_events": 0, "trade_events_at_or_below_bid": 0, "first_fill_evidence_at_utc": None, "first_fill_evidence_source": None}
    else:
        events = document["events"] if isinstance(document, dict) else document
        event = next(item for item in events if item["slug"] == slug)
        markets = [m for m in event["markets"] if m.get("active") and not m.get("closed") and m.get("acceptingOrders") and m.get("enableOrderBook")]
        if "other" not in [str(m.get("groupItemTitle") or "").lower() for m in markets]:
            raise ValueError("event requires an explicit active Other leg")
        for market in markets:
            outcomes, tokens = json.loads(market["outcomes"]), json.loads(market["clobTokenIds"])
            token = tokens[outcomes.index("Yes")]
            legs[token] = {"name": market["groupItemTitle"], "tick": float(market["orderPriceMinTickSize"]), "paper_bid": None, "cross_events": 0, "trade_events_at_or_below_bid": 0, "first_fill_evidence_at_utc": None, "first_fill_evidence_source": None}
    counts = {}
    started = datetime.now(timezone.utc)
    async with connect(WS_URL, origin="https://polymarket.com", ping_interval=None, open_timeout=20) as socket:
        await socket.send(json.dumps({"assets_ids": list(legs), "type": "market", "custom_feature_enabled": True}))

        async def heartbeat() -> None:
            while True:
                await asyncio.sleep(10)
                await socket.send("PING")

        heart = asyncio.create_task(heartbeat())
        try:
            async with asyncio.timeout(seconds):
                while True:
                    message = await socket.recv()
                    if message == "PONG":
                        counts["PONG"] = counts.get("PONG", 0) + 1
                        continue
                    decoded = json.loads(message)
                    items = decoded if isinstance(decoded, list) else [decoded]
                    for item in items:
                        kind = item.get("event_type", "unknown")
                        counts[kind] = counts.get(kind, 0) + 1
                        token = str(item.get("asset_id", ""))
                        leg = legs.get(token)
                        if kind == "book" and leg is not None and leg["paper_bid"] is None:
                            bids = [float(level["price"]) for level in item.get("bids", [])]
                            asks = [float(level["price"]) for level in item.get("asks", [])]
                            if bids and asks:
                                bid, ask = max(bids), min(asks)
                                leg["paper_bid"] = max(bid, round(ask - leg["tick"], 10))
                        else:
                            apply_market_message(item, legs)
        except TimeoutError:
            pass
        finally:
            heart.cancel()
    if any(leg["paper_bid"] is None for leg in legs.values()):
        raise RuntimeError("did not receive an initial book for every leg")
    result = summarize_leg_risk(legs)
    record = {
        "schema_version": 1,
        "record_type": "aggressive_forward_websocket_paper_fill_probe",
        "observed_from_utc": started.isoformat().replace("+00:00", "Z"),
        "observed_until_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "event": {"title": event["title"], "slug": event["slug"], "leg_count": len(legs)},
        "method": {"quote_policy": "one_tick_below_initial_best_ask", "fill_evidence": "public best-ask cross in best_bid_ask or price_change, or SELL trade at/below paper bid; queue position and filled size are unknown", "message_counts": counts, "orders_placed": 0, "authentication_used": False},
        "legs": list(legs.values()),
        "result": result,
        "capital_authorized": False,
        "decision": "review_for_tiny_capital" if result["all_legs_with_fill_evidence"] else "continue_or_reprice_paper_test",
    }
    write_record(output, record)
    print(json.dumps(record["result"] | {"message_counts": counts}, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 5:
        raise SystemExit("usage: ws_paper_fill_probe.py SNAPSHOT SLUG SECONDS OUTPUT")
    asyncio.run(run(Path(sys.argv[1]), sys.argv[2], float(sys.argv[3]), Path(sys.argv[4])))
