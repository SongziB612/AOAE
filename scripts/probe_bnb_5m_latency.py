"""Capture one full BNB five-minute market using public Chainlink RTDS and CLOB books."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from websockets.asyncio.client import connect

from aoae.experiment import write_record
from aoae.latency_probe import evaluate_decision_points, parse_chainlink_ticks, websocket_capture_is_technically_complete
from aoae.orderbook import apply_book_message, empty_book, top_of_book


GAMMA = "https://gamma-api.polymarket.com/markets"
CLOB = "https://clob.polymarket.com"
RTDS = "wss://ws-live-data.polymarket.com"
CLOB_WS = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
USER_AGENT = "AOAE/0.1 read-only-research"


def fetch_json(url: str, attempts: int = 3) -> object:
    error = None
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read())
        except OSError as exc:
            error = exc
            time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"public endpoint unavailable: {url}") from error


def discover_market(slug: str, deadline_epoch: float) -> dict:
    urls = [
        f"{GAMMA}/slug/{slug}",
        GAMMA + "?" + urlencode({"slug": slug}),
        f"{GAMMA.rsplit('/', 1)[0]}/events/slug/{slug}",
    ]
    last_error: Exception | None = None
    while time.time() < deadline_epoch:
        for url in urls:
            try:
                data = fetch_json(url)
                if isinstance(data, list) and data:
                    return data[0]
                if isinstance(data, dict) and data.get("conditionId"):
                    return data
                if isinstance(data, dict):
                    markets = data.get("markets") or []
                    matching = next((item for item in markets if item.get("slug") == slug), None)
                    if matching:
                        return matching
            except RuntimeError as exc:
                # Use every documented slug lookup before discarding a market.
                last_error = exc
        time.sleep(2)
    detail = f"; last_error={last_error}" if last_error else ""
    raise RuntimeError(f"market was not published before deadline: {slug}{detail}")


def decode_list(value: object) -> list:
    return json.loads(value) if isinstance(value, str) else list(value)


def fee_terms(market: dict) -> tuple[float, float, dict]:
    schedule = market.get("feeSchedule") or {}
    if isinstance(schedule, str):
        schedule = json.loads(schedule)
    rate = schedule.get("rate")
    exponent = schedule.get("exponent", 1)
    source = "gamma_feeSchedule"
    details = schedule
    if rate is None:
        details = fetch_json(f"{CLOB}/clob-markets/{market['conditionId']}")
        curve = details.get("fd") or {}
        rate, exponent, source = curve.get("r"), curve.get("e", 1), "clob_market_info"
    if rate is None:
        raise RuntimeError("market fee parameters are absent")
    return float(rate), float(exponent), {"source": source, "raw": details}


def fetch_books(tokens: dict[str, str]) -> dict[str, dict]:
    captured = {}
    for outcome, token in tokens.items():
        book = fetch_json(f"{CLOB}/book?" + urlencode({"token_id": token}))
        asks = [(float(level["price"]), float(level["size"])) for level in book.get("asks", [])]
        bids = [(float(level["price"]), float(level["size"])) for level in book.get("bids", [])]
        captured[outcome] = {
            "ask": min(asks)[0] if asks else None,
            "ask_size": min(asks)[1] if asks else None,
            "bid": max(bids)[0] if bids else None,
            "bid_size": max(bids)[1] if bids else None,
        }
    return captured


async def capture(spec: dict, output: Path, requested_start_epoch: int | None = None) -> dict:
    interval = int(spec["interval_seconds"])
    now = time.time()
    start_epoch = requested_start_epoch or (int(now) // interval + 1) * interval
    end_epoch = start_epoch + interval
    slug = spec["market_slug_prefix"] + str(start_epoch)
    if requested_start_epoch is not None:
        await asyncio.sleep(max(0, start_epoch - time.time() - 20))
    market = await asyncio.to_thread(discover_market, slug, start_epoch + 30)
    outcomes, token_ids = decode_list(market["outcomes"]), decode_list(market["clobTokenIds"])
    tokens = dict(zip(outcomes, token_ids, strict=True))
    if set(tokens) != {"Up", "Down"}:
        raise RuntimeError(f"unexpected outcomes: {sorted(tokens)}")
    fee_rate, fee_exponent, fee_capture = await asyncio.to_thread(fee_terms, market)
    ticks: list[dict] = []
    snapshots: list[dict] = []
    errors: list[str] = []
    book_message_counts: dict[str, int] = {}
    # The exact-boundary RTDS tick arrived about two seconds late in the engineering
    # probe. Three seconds captures it while allowing consecutive markets.
    stop_epoch = end_epoch + min(3, int(spec["settlement_tick_tolerance_seconds"]))

    async def oracle_reader() -> None:
        subscription = {
            "action": "subscribe",
            "subscriptions": [{
                "topic": "crypto_prices_chainlink",
                "type": "*",
                "filters": json.dumps({"symbol": spec["chainlink_symbol"]}, separators=(",", ":")),
            }],
        }
        try:
            async with connect(RTDS, open_timeout=30, ping_interval=20, ping_timeout=20) as socket:
                await socket.send(json.dumps(subscription))
                while time.time() < stop_epoch:
                    remaining = max(0.1, stop_epoch - time.time())
                    try:
                        raw = await asyncio.wait_for(socket.recv(), timeout=min(30, remaining))
                    except TimeoutError:
                        continue
                    received = int(time.time() * 1000)
                    for tick in parse_chainlink_ticks(raw, spec["chainlink_symbol"]):
                        tick["received_timestamp_ms"] = received
                        ticks.append(tick)
        except Exception as exc:
            errors.append(f"oracle:{type(exc).__name__}:{exc}")

    async def book_reader() -> None:
        await asyncio.sleep(max(0, start_epoch - time.time()))
        while time.time() <= end_epoch:
            requested = int(time.time() * 1000)
            try:
                books = await asyncio.to_thread(fetch_books, tokens)
                reference = max((tick for tick in ticks if tick["timestamp_ms"] <= requested), key=lambda item: item["timestamp_ms"], default=None)
                snapshots.append({
                    "timestamp_ms": int(time.time() * 1000),
                    "reference_timestamp_ms": reference["timestamp_ms"] if reference else None,
                    "reference_price": reference["value"] if reference else None,
                    "up_bid": books["Up"]["bid"], "up_bid_size": books["Up"]["bid_size"],
                    "up_ask": books["Up"]["ask"], "up_ask_size": books["Up"]["ask_size"],
                    "down_bid": books["Down"]["bid"], "down_bid_size": books["Down"]["bid_size"],
                    "down_ask": books["Down"]["ask"], "down_ask_size": books["Down"]["ask_size"],
                })
            except Exception as exc:
                errors.append(f"book:{type(exc).__name__}:{exc}")
            await asyncio.sleep(float(spec["book_poll_seconds"]))

    async def websocket_books() -> None:
        state = {token: empty_book() for token in tokens.values()}

        async def reader() -> None:
            nonlocal state
            while time.time() < stop_epoch:
                heart = None
                # Never sample a stale pre-disconnect book as though it were live.
                state = {token: empty_book() for token in tokens.values()}
                try:
                    async with connect(CLOB_WS, origin="https://polymarket.com", open_timeout=30, ping_interval=None) as socket:
                        await socket.send(json.dumps({"assets_ids": list(tokens.values()), "type": "market", "custom_feature_enabled": True}))

                        async def heartbeat() -> None:
                            while True:
                                await asyncio.sleep(10)
                                await socket.send("PING")

                        heart = asyncio.create_task(heartbeat())
                        while time.time() < stop_epoch:
                            try:
                                raw = await asyncio.wait_for(socket.recv(), timeout=min(30, max(.1, stop_epoch - time.time())))
                            except TimeoutError:
                                continue
                            if raw == "PONG":
                                book_message_counts["PONG"] = book_message_counts.get("PONG", 0) + 1
                                continue
                            decoded = json.loads(raw)
                            for message in decoded if isinstance(decoded, list) else [decoded]:
                                kind = message.get("event_type", "unknown")
                                book_message_counts[kind] = book_message_counts.get(kind, 0) + 1
                                apply_book_message(message, state)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    errors.append(f"clob_ws:{type(exc).__name__}:{exc}")
                finally:
                    if heart is not None:
                        heart.cancel()
                        await asyncio.gather(heart, return_exceptions=True)
                if time.time() < stop_epoch:
                    book_message_counts["RECONNECT"] = book_message_counts.get("RECONNECT", 0) + 1
                    await asyncio.sleep(min(1.0, max(0.0, stop_epoch - time.time())))

        async def sampler() -> None:
            await asyncio.sleep(max(0, start_epoch - time.time()))
            while time.time() <= end_epoch:
                captured = int(time.time() * 1000)
                reference = max((tick for tick in ticks if tick["timestamp_ms"] <= captured), key=lambda item: item["timestamp_ms"], default=None)
                up, down = top_of_book(state[tokens["Up"]]), top_of_book(state[tokens["Down"]])
                snapshots.append({
                    "timestamp_ms": captured,
                    "reference_timestamp_ms": reference["timestamp_ms"] if reference else None,
                    "reference_price": reference["value"] if reference else None,
                    "up_bid": up["bid"], "up_bid_size": up["bid_size"], "up_ask": up["ask"], "up_ask_size": up["ask_size"],
                    "down_bid": down["bid"], "down_bid_size": down["bid_size"], "down_ask": down["ask"], "down_ask_size": down["ask_size"],
                })
                await asyncio.sleep(float(spec.get("book_sample_seconds", .25)))

        await asyncio.gather(reader(), sampler())

    transport = spec.get("book_transport", "rest")
    await asyncio.gather(oracle_reader(), websocket_books() if transport == "websocket" else book_reader())
    unique_ticks = {tick["timestamp_ms"]: tick for tick in ticks}
    ticks = sorted(unique_ticks.values(), key=lambda item: item["timestamp_ms"])
    tolerance_ms = int(spec["settlement_tick_tolerance_seconds"]) * 1000
    opening = min((tick for tick in ticks if start_epoch * 1000 <= tick["timestamp_ms"] <= start_epoch * 1000 + tolerance_ms), key=lambda item: item["timestamp_ms"], default=None)
    closing = max((tick for tick in ticks if end_epoch * 1000 - tolerance_ms <= tick["timestamp_ms"] <= end_epoch * 1000), key=lambda item: item["timestamp_ms"], default=None)
    points = []
    if opening and closing:
        points = evaluate_decision_points(
            snapshots, opening["value"], closing["value"], end_epoch * 1000,
            spec["decision_seconds_before_end"], fee_rate, fee_exponent,
        )
    # A missing ask at a preregistered offset is an economically meaningful
    # no-trade observation, not a failed capture.  Only missing reference ticks,
    # missing decision points, or a websocket session with no book events makes
    # the market technically incomplete.
    book_events = sum(
        value for kind, value in book_message_counts.items()
        if kind not in {"PONG", "RECONNECT"}
    )
    complete = bool(
        opening
        and closing
        and snapshots
        and len(points) == len(spec["decision_seconds_before_end"])
        and all(point.get("status") in {"QUOTED_ONLY", "NO_ASK"} for point in points)
        and (transport != "websocket" or book_events > 0)
    )
    record = {
        "schema_version": 1,
        "record_type": "read_only_bnb_five_minute_latency_probe",
        "captured_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "market": {
            "slug": slug, "question": market.get("question"), "condition_id": market.get("conditionId"),
            "start_epoch": start_epoch, "end_epoch": end_epoch, "tokens": tokens,
            "resolution_source": market.get("resolutionSource"), "description": market.get("description"),
        },
        "fee": {"rate": fee_rate, "exponent": fee_exponent, **fee_capture},
        "method": {
            "decision_seconds_before_end": spec["decision_seconds_before_end"],
            "book_transport": transport,
            "book_poll_seconds": spec.get("book_poll_seconds"), "book_sample_seconds": spec.get("book_sample_seconds"), "orders_placed": 0,
            "authentication_used": False, "quoted_prices_are_fills": False,
        },
        "reference": {"opening_tick": opening, "closing_tick": closing, "tick_count": len(ticks)},
        "evidence": {"chainlink_ticks": ticks, "book_snapshots": snapshots},
        "decision_points": points,
        "diagnostics": {"book_snapshots": len(snapshots), "book_message_counts": book_message_counts, "errors": errors[-20:]},
        "result": {
            "status": "ENGINEERING_PROBE_COMPLETE" if complete else "INCOMPLETE_CAPTURE",
            "profitable_quoted_points": sum(item.get("quoted_net_pnl_per_share", 0) > 0 for item in points),
            "deployable": False,
            "reason": "One market cannot satisfy the preregistered 100-market evidence gate, and quoted asks are not fills.",
        },
        "capital_authorized": False,
        "decision": "collect_100_independent_markets" if complete else "repair_capture_before_expansion",
    }
    write_record(output, record)
    return record


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: probe_bnb_5m_latency.py SPEC OUTPUT")
    spec_path, output = map(Path, sys.argv[1:])
    spec = json.loads(spec_path.read_bytes())
    if spec.get("orders_authorized") is not False or spec.get("authentication_authorized") is not False or spec.get("capital_authorized") is not False:
        raise ValueError("probe requires zero orders, zero authentication, and zero capital")
    count = int(spec.get("market_count", 1))
    if count == 1:
        result = asyncio.run(capture(spec, output))
        print(json.dumps(result["result"] | result["diagnostics"], indent=2))
        return 0
    interval = int(spec["interval_seconds"])
    market_directory = output.parent / "markets"
    existing_paths = sorted(market_directory.glob("*.json"), key=lambda path: int(path.stem))
    attempted_records = [json.loads(path.read_text(encoding="utf-8")) for path in existing_paths]
    existing_records = [
        record for record in attempted_records
        if websocket_capture_is_technically_complete(record, spec["decision_seconds_before_end"])
    ]
    if len(existing_records) > count:
        raise RuntimeError(f"refusing ambiguous resume: found {len(existing_records)} valid records for a {count}-market batch")
    next_boundary = (int(time.time()) // interval + 1) * interval
    first_start = max(next_boundary, int(existing_paths[-1].stem) + interval if existing_paths else next_boundary)
    async def run_batch() -> tuple[list[dict], list[dict]]:
        records = list(existing_records)
        failures = [
            {"start_epoch": record["market"]["start_epoch"], "error": "INCOMPLETE_CAPTURE"}
            for record in attempted_records
            if not websocket_capture_is_technically_complete(record, spec["decision_seconds_before_end"])
        ]
        next_attempt_start = first_start
        attempts = len(attempted_records)
        maximum_attempts = count * 3

        async def run_one(start: int) -> None:
            market_output = output.parent / "markets" / f"{start}.json"
            try:
                record = await capture(spec, market_output, start)
                if record["result"]["status"] == "ENGINEERING_PROBE_COMPLETE":
                    records.append(record)
                else:
                    failures.append({"start_epoch": start, "error": "INCOMPLETE_CAPTURE"})
                print(json.dumps({"valid": len(records), "target": count, "attempted": len(records) + len(failures), "slug": record["market"]["slug"], "status": record["result"]["status"]}), flush=True)
            except Exception as exc:
                failures.append({"start_epoch": start, "error": f"{type(exc).__name__}:{exc}"})
                print(json.dumps({"valid": len(records), "target": count, "attempted": len(records) + len(failures), "start_epoch": start, "error": failures[-1]["error"]}), flush=True)

        while len(records) < count and attempts < maximum_attempts:
            batch_size = min(count - len(records), maximum_attempts - attempts)
            starts = [next_attempt_start + index * interval for index in range(batch_size)]
            next_attempt_start += batch_size * interval
            attempts += batch_size
            await asyncio.gather(*(run_one(start) for start in starts))
        records.sort(key=lambda record: record["market"]["start_epoch"])
        failures.sort(key=lambda item: item["start_epoch"])
        return records[:count], failures

    records, failures = asyncio.run(run_batch())
    by_offset = {}
    for offset in spec["decision_seconds_before_end"]:
        points = [point for record in records for point in record["decision_points"] if point["seconds_before_end"] == offset and point["status"] == "QUOTED_ONLY"]
        by_offset[str(offset)] = {
            "quoted_markets": len(points),
            "correct_signals": sum(point["signal_correct"] for point in points),
            "total_quoted_net_pnl_per_one_share_each": sum(point["quoted_net_pnl_per_share"] for point in points),
        }
    aggregate = {
        "schema_version": 1,
        "record_type": "read_only_bnb_five_minute_latency_batch",
        "captured_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "requested_markets": count,
        "completed_markets": len(records),
        "failures": failures,
        "by_decision_seconds_before_end": by_offset,
        "market_result_paths": [str((output.parent / "markets" / f"{record['market']['start_epoch']}.json").relative_to(output.parent)) for record in records],
        "result": {"deployable": False, "gate_evaluated": len(records) == count, "reason": "Batch evidence still requires independent replay and fill/latency simulation."},
        "orders_placed": 0,
        "authentication_used": False,
        "capital_authorized": False,
        "decision": "independent_replay" if len(records) == count else "repair_missing_markets",
    }
    write_record(output, aggregate)
    print(json.dumps(aggregate["result"] | {"completed_markets": len(records), "failures": len(failures)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
