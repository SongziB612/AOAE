"""Pure calculations for short-horizon prediction-market latency probes."""

from __future__ import annotations

import json
from typing import Any, Iterable


def websocket_capture_is_technically_complete(record: dict[str, Any], expected_offsets: Iterable[int]) -> bool:
    """Classify legacy REST and WebSocket captures without treating no ask as data loss."""
    reference = record.get("reference") or {}
    points = record.get("decision_points") or []
    expected = [int(offset) for offset in expected_offsets]
    observed = [int(point.get("seconds_before_end", -1)) for point in points]
    snapshots = (record.get("evidence") or {}).get("book_snapshots") or []
    base_complete = bool(
        reference.get("opening_tick")
        and reference.get("closing_tick")
        and snapshots
        and observed == expected
        and all(point.get("status") in {"QUOTED_ONLY", "NO_ASK"} for point in points)
    )
    transport = (record.get("method") or {}).get("book_transport") or "rest"
    if transport != "websocket":
        return base_complete
    counts = (record.get("diagnostics") or {}).get("book_message_counts") or {}
    book_events = sum(int(value) for kind, value in counts.items() if kind not in {"PONG", "RECONNECT"})
    return base_complete and book_events > 0


def parse_chainlink_ticks(raw: str | bytes, expected_symbol: str) -> list[dict[str, Any]]:
    """Parse public Polymarket RTDS Chainlink payloads without assuming one envelope shape."""
    if raw in ("", b"", "PONG", b"PONG"):
        return []
    try:
        message = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []
    if not isinstance(message, dict):
        return []
    if message.get("topic") != "crypto_prices_chainlink":
        return []
    payload = message.get("payload") or {}
    candidates = payload.get("data") if isinstance(payload.get("data"), list) else [payload]
    expected = expected_symbol.strip().lower()
    ticks = []
    for item in candidates:
        if not isinstance(item, dict) or str(item.get("symbol", payload.get("symbol", ""))).lower() != expected:
            continue
        value = item.get("value")
        timestamp = item.get("timestamp", message.get("timestamp"))
        if value is None or timestamp is None or float(value) <= 0:
            continue
        ticks.append({"symbol": expected, "timestamp_ms": int(timestamp), "value": float(value)})
    return ticks


def taker_fee_per_share(price: float, rate: float, exponent: float = 1.0) -> float:
    if not 0 < price < 1 or rate < 0 or exponent <= 0:
        raise ValueError("invalid fee inputs")
    return rate * (price * (1 - price)) ** exponent


def nearest_at_or_before(rows: Iterable[dict[str, Any]], timestamp_ms: int) -> dict[str, Any] | None:
    eligible = [row for row in rows if int(row["timestamp_ms"]) <= timestamp_ms]
    return max(eligible, key=lambda row: int(row["timestamp_ms"]), default=None)


def evaluate_decision_points(
    snapshots: list[dict[str, Any]],
    opening_price: float,
    final_price: float,
    end_timestamp_ms: int,
    offsets_seconds: Iterable[int],
    fee_rate: float,
    fee_exponent: float = 1.0,
) -> list[dict[str, Any]]:
    """Evaluate every preregistered point; this is quoted paper PnL, not a fill claim."""
    winner = "Up" if final_price >= opening_price else "Down"
    results = []
    for offset in offsets_seconds:
        target = end_timestamp_ms - int(offset) * 1000
        row = nearest_at_or_before(snapshots, target)
        if row is None or row.get("reference_price") is None:
            results.append({"seconds_before_end": int(offset), "status": "MISSING"})
            continue
        signal = "Up" if float(row["reference_price"]) >= opening_price else "Down"
        ask = row.get("up_ask") if signal == "Up" else row.get("down_ask")
        if ask is None:
            results.append({"seconds_before_end": int(offset), "status": "NO_ASK", "signal": signal})
            continue
        ask = float(ask)
        fee = taker_fee_per_share(ask, fee_rate, fee_exponent)
        pnl = (1.0 if signal == winner else 0.0) - ask - fee
        results.append({
            "seconds_before_end": int(offset),
            "status": "QUOTED_ONLY",
            "snapshot_timestamp_ms": int(row["timestamp_ms"]),
            "signal": signal,
            "winner": winner,
            "signal_correct": signal == winner,
            "ask": ask,
            "fee_per_share": fee,
            "quoted_net_pnl_per_share": pnl,
        })
    return results


def simulate_delayed_taker(
    snapshots: list[dict[str, Any]],
    decision_point: dict[str, Any],
    delay_ms: int,
    shares: float,
    fee_rate: float,
    fee_exponent: float = 1.0,
) -> dict[str, Any]:
    """Reprice a visible quote at the first captured book after a fixed delay."""
    if delay_ms < 0 or shares <= 0:
        raise ValueError("delay and shares must be non-negative/positive")
    if decision_point.get("status") != "QUOTED_ONLY":
        return {"status": "NO_INITIAL_QUOTE", "delay_ms": delay_ms}
    side = str(decision_point["signal"]).lower()
    decision_ts = int(decision_point["snapshot_timestamp_ms"])
    initial = next((row for row in snapshots if int(row["timestamp_ms"]) == decision_ts), None)
    if initial is None or initial.get(f"{side}_ask_size") is None or float(initial[f"{side}_ask_size"]) < shares:
        return {"status": "INSUFFICIENT_INITIAL_DEPTH", "delay_ms": delay_ms}
    execution = min((row for row in snapshots if int(row["timestamp_ms"]) >= decision_ts + delay_ms), key=lambda row: int(row["timestamp_ms"]), default=None)
    if execution is None or execution.get(f"{side}_ask") is None or execution.get(f"{side}_ask_size") is None or float(execution[f"{side}_ask_size"]) < shares:
        return {"status": "NO_EXECUTABLE_ASK", "delay_ms": delay_ms}
    price = float(execution[f"{side}_ask"])
    per_share_fee = taker_fee_per_share(price, fee_rate, fee_exponent)
    pnl = shares * ((1.0 if decision_point["signal_correct"] else 0.0) - price - per_share_fee)
    return {
        "status": "SIMULATED_REPRICE",
        "delay_ms": delay_ms,
        "execution_snapshot_timestamp_ms": int(execution["timestamp_ms"]),
        "actual_sample_delay_ms": int(execution["timestamp_ms"]) - decision_ts,
        "price": price,
        "shares": shares,
        "fee": shares * per_share_fee,
        "net_pnl": pnl,
    }
