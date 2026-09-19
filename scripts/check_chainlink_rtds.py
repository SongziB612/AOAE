"""Short read-only connectivity check for Polymarket's public Chainlink RTDS topic."""

import asyncio
import json
import sys
import time

from websockets.asyncio.client import connect

from aoae.latency_probe import parse_chainlink_ticks


async def run(seconds: float, symbol: str) -> int:
    ticks = []
    subscription = {
        "action": "subscribe",
        "subscriptions": [{
            "topic": "crypto_prices_chainlink",
            "type": "*",
            "filters": json.dumps({"symbol": symbol}, separators=(",", ":")),
        }],
    }
    stop = time.time() + seconds
    async with connect("wss://ws-live-data.polymarket.com", open_timeout=30, ping_interval=20) as socket:
        await socket.send(json.dumps(subscription))
        while time.time() < stop:
            try:
                raw = await asyncio.wait_for(socket.recv(), timeout=max(0.1, stop - time.time()))
            except TimeoutError:
                break
            ticks.extend(parse_chainlink_ticks(raw, symbol))
    print(json.dumps({"symbol": symbol, "tick_count": len(ticks), "first": ticks[0] if ticks else None, "last": ticks[-1] if ticks else None}, indent=2))
    return 0 if ticks else 1


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: check_chainlink_rtds.py SECONDS SYMBOL")
    raise SystemExit(asyncio.run(run(float(sys.argv[1]), sys.argv[2])))
