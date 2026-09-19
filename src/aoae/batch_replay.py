"""Independent replay and conservative execution simulation for latency batches."""

from __future__ import annotations

from typing import Any, Iterable


def fee_per_share(price: float, rate: float, exponent: float) -> float:
    if not 0 < price < 1 or rate < 0 or exponent <= 0:
        raise ValueError("invalid fee inputs")
    return rate * (price * (1 - price)) ** exponent


def replay_points(record: dict[str, Any], offsets: Iterable[int]) -> list[dict[str, Any]]:
    """Recompute signals and quoted PnL without calling the capture evaluator."""
    snapshots = sorted(record["evidence"]["book_snapshots"], key=lambda row: int(row["timestamp_ms"]))
    opening = float(record["reference"]["opening_tick"]["value"])
    closing = float(record["reference"]["closing_tick"]["value"])
    end_ms = int(record["market"]["end_epoch"]) * 1000
    rate = float(record["fee"]["rate"])
    exponent = float(record["fee"].get("exponent", 1.0))
    winner = "Up" if closing >= opening else "Down"
    output: list[dict[str, Any]] = []
    for offset in offsets:
        target = end_ms - int(offset) * 1000
        candidates = [row for row in snapshots if int(row["timestamp_ms"]) <= target]
        row = candidates[-1] if candidates else None
        if row is None or row.get("reference_price") is None:
            output.append({"seconds_before_end": int(offset), "status": "MISSING"})
            continue
        signal = "Up" if float(row["reference_price"]) >= opening else "Down"
        side = signal.lower()
        ask = row.get(f"{side}_ask")
        if ask is None:
            output.append({"seconds_before_end": int(offset), "status": "NO_ASK", "signal": signal})
            continue
        ask = float(ask)
        fee = fee_per_share(ask, rate, exponent)
        correct = signal == winner
        output.append({
            "seconds_before_end": int(offset),
            "status": "QUOTED_ONLY",
            "snapshot_timestamp_ms": int(row["timestamp_ms"]),
            "signal": signal,
            "winner": winner,
            "signal_correct": correct,
            "ask": ask,
            "fee_per_share": fee,
            "quoted_net_pnl_per_share": (1.0 if correct else 0.0) - ask - fee,
        })
    return output


def compare_points(stored: list[dict[str, Any]], replayed: list[dict[str, Any]], tolerance: float = 1e-9) -> list[str]:
    """Return field-level replay mismatches."""
    mismatches: list[str] = []
    if len(stored) != len(replayed):
        return [f"point_count:{len(stored)}!={len(replayed)}"]
    exact = ("seconds_before_end", "status", "snapshot_timestamp_ms", "signal", "winner", "signal_correct")
    numeric = ("ask", "fee_per_share", "quoted_net_pnl_per_share")
    for index, (left, right) in enumerate(zip(stored, replayed)):
        for field in exact:
            if left.get(field) != right.get(field):
                mismatches.append(f"{index}:{field}:{left.get(field)}!={right.get(field)}")
        for field in numeric:
            if field in left or field in right:
                if field not in left or field not in right or abs(float(left[field]) - float(right[field])) > tolerance:
                    mismatches.append(f"{index}:{field}:{left.get(field)}!={right.get(field)}")
    return mismatches


def simulate_taker(
    record: dict[str, Any],
    point: dict[str, Any],
    delay_ms: int,
    shares: float,
    adverse_slippage: float,
) -> dict[str, Any]:
    """Require displayed depth, reprice after delay, and charge adverse slippage."""
    if point.get("status") != "QUOTED_ONLY":
        return {"status": "NO_INITIAL_QUOTE", "attempted": False, "pnl": 0.0}
    snapshots = sorted(record["evidence"]["book_snapshots"], key=lambda row: int(row["timestamp_ms"]))
    side = str(point["signal"]).lower()
    decision_ms = int(point["snapshot_timestamp_ms"])
    initial = next((row for row in snapshots if int(row["timestamp_ms"]) == decision_ms), None)
    size_field = f"{side}_ask_size"
    ask_field = f"{side}_ask"
    if initial is None or initial.get(size_field) is None or float(initial[size_field]) < shares:
        return {"status": "INSUFFICIENT_INITIAL_DEPTH", "attempted": False, "pnl": 0.0}
    execution = next((row for row in snapshots if int(row["timestamp_ms"]) >= decision_ms + delay_ms), None)
    if execution is None or execution.get(ask_field) is None or execution.get(size_field) is None or float(execution[size_field]) < shares:
        return {"status": "NO_EXECUTABLE_ASK", "attempted": True, "pnl": 0.0}
    visible_ask = float(execution[ask_field])
    execution_price = min(0.99, visible_ask + adverse_slippage)
    rate = float(record["fee"]["rate"])
    exponent = float(record["fee"].get("exponent", 1.0))
    fee = shares * fee_per_share(execution_price, rate, exponent)
    pnl = shares * ((1.0 if point["signal_correct"] else 0.0) - execution_price) - fee
    return {
        "status": "SIMULATED_REPRICE",
        "attempted": True,
        "pnl": pnl,
        "visible_ask": visible_ask,
        "execution_price": execution_price,
        "execution_timestamp_ms": int(execution["timestamp_ms"]),
        "actual_delay_ms": int(execution["timestamp_ms"]) - decision_ms,
        "fee": fee,
    }


def maximum_drawdown(pnls: Iterable[float]) -> float:
    equity = peak = drawdown = 0.0
    for value in pnls:
        equity += float(value)
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown
