"""Causal state features for whether a short-horizon signal remains tradeable."""

from __future__ import annotations

import math
from typing import Any


FEATURE_NAMES = (
    "absolute_displacement_bps",
    "signal_aligned_velocity_10s_bps",
    "realized_absolute_variation_30s_bps",
    "signal_flip_count_30s",
    "top_of_book_change_acceleration_5s_vs_20s",
    "binary_market_overround",
    "signed_top_depth_imbalance",
    "signaled_ask",
)


def _last_at_or_before(rows: list[dict[str, Any]], timestamp_ms: int, time_key: str) -> dict[str, Any] | None:
    return max((row for row in rows if int(row[time_key]) <= timestamp_ms), key=lambda row: int(row[time_key]), default=None)


def extract_predictability_state(record: dict[str, Any], seconds_before_end: int = 120, minimum_depth: float = 5) -> dict[str, Any]:
    """Extract features using only messages received by the decision snapshot."""
    point = next((item for item in record["decision_points"] if int(item["seconds_before_end"]) == seconds_before_end), None)
    if point is None or point.get("status") != "QUOTED_ONLY":
        return {"eligible": False, "reason": "no_initial_quote"}
    decision_ms = int(point["snapshot_timestamp_ms"])
    snapshot = next((row for row in record["evidence"]["book_snapshots"] if int(row["timestamp_ms"]) == decision_ms), None)
    if snapshot is None:
        return {"eligible": False, "reason": "decision_snapshot_missing"}
    side = str(point["signal"]).lower()
    opposite = "down" if side == "up" else "up"
    side_depth = snapshot.get(f"{side}_ask_size")
    if side_depth is None or float(side_depth) < minimum_depth:
        return {"eligible": False, "reason": "insufficient_initial_depth"}
    opening = record["reference"].get("opening_tick")
    if opening is None:
        return {"eligible": False, "reason": "opening_tick_missing"}
    ticks = sorted(
        (tick for tick in record["evidence"]["chainlink_ticks"] if int(tick["received_timestamp_ms"]) <= decision_ms),
        key=lambda tick: int(tick["received_timestamp_ms"]),
    )
    latest = ticks[-1] if ticks else None
    ten_seconds_ago = _last_at_or_before(ticks, decision_ms - 10_000, "received_timestamp_ms")
    recent = [tick for tick in ticks if int(tick["received_timestamp_ms"]) >= decision_ms - 30_000]
    if latest is None or ten_seconds_ago is None or len(recent) < 2:
        return {"eligible": False, "reason": "insufficient_causal_reference_history"}
    opening_price, current_price = float(opening["value"]), float(latest["value"])
    direction = 1 if side == "up" else -1
    log_values = [math.log(float(tick["value"])) for tick in recent]
    abs_variation = sum(abs(right - left) for left, right in zip(log_values, log_values[1:])) * 10_000
    signs = [float(tick["value"]) >= opening_price for tick in recent]
    flips = sum(left != right for left, right in zip(signs, signs[1:]))
    book_rows = [row for row in record["evidence"]["book_snapshots"] if decision_ms - 20_000 <= int(row["timestamp_ms"]) <= decision_ms]

    def change_count(window_ms: int) -> int:
        rows = [row for row in book_rows if int(row["timestamp_ms"]) >= decision_ms - window_ms]
        keys = ("up_bid", "up_ask", "down_bid", "down_ask")
        return sum(any(left.get(key) != right.get(key) for key in keys) for left, right in zip(rows, rows[1:]))

    changes_5, changes_20 = change_count(5_000), change_count(20_000)
    opposite_depth = float(snapshot.get(f"{opposite}_ask_size") or 0)
    depth_total = float(side_depth) + opposite_depth
    up_ask, down_ask = snapshot.get("up_ask"), snapshot.get("down_ask")
    if up_ask is None or down_ask is None:
        return {"eligible": False, "reason": "two_sided_ask_missing"}
    features = {
        "absolute_displacement_bps": abs(math.log(current_price / opening_price)) * 10_000,
        "signal_aligned_velocity_10s_bps": direction * math.log(current_price / float(ten_seconds_ago["value"])) * 10_000,
        "realized_absolute_variation_30s_bps": abs_variation,
        "signal_flip_count_30s": float(flips),
        "top_of_book_change_acceleration_5s_vs_20s": changes_5 / max(changes_20 / 4, 1),
        "binary_market_overround": float(up_ask) + float(down_ask) - 1,
        "signed_top_depth_imbalance": (float(side_depth) - opposite_depth) / depth_total if depth_total else 0,
        "signaled_ask": float(snapshot[f"{side}_ask"]),
    }
    return {
        "eligible": True,
        "market_slug": record["market"]["slug"],
        "decision_timestamp_ms": decision_ms,
        "signal_correct": bool(point["signal_correct"]),
        "features": features,
    }
