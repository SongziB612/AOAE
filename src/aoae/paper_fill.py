"""Conservative fill-evidence accounting for read-only market probes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def utc_from_milliseconds(value: Any) -> str:
    """Return a canonical UTC timestamp, falling back to observation time."""
    try:
        moment = datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        moment = datetime.now(timezone.utc)
    return moment.isoformat().replace("+00:00", "Z")


def record_cross(leg: dict[str, Any], best_ask: Any, timestamp: Any, source: str) -> None:
    """Record evidence that a public ask reached a hypothetical resting buy."""
    if leg.get("paper_bid") is None or best_ask in (None, ""):
        return
    if float(best_ask) <= float(leg["paper_bid"]):
        leg["cross_events"] += 1
        if leg.get("first_fill_evidence_at_utc") is None:
            leg["first_fill_evidence_at_utc"] = utc_from_milliseconds(timestamp)
            leg["first_fill_evidence_source"] = source


def apply_market_message(item: dict[str, Any], legs: dict[str, dict[str, Any]]) -> None:
    """Apply one documented Polymarket market-channel message."""
    kind = item.get("event_type", "unknown")
    if kind == "price_change":
        for change in item.get("price_changes", []):
            leg = legs.get(str(change.get("asset_id", "")))
            if leg is not None:
                record_cross(leg, change.get("best_ask"), item.get("timestamp"), "price_change.best_ask")
        return

    leg = legs.get(str(item.get("asset_id", "")))
    if leg is None:
        return
    if kind == "best_bid_ask":
        record_cross(leg, item.get("best_ask"), item.get("timestamp"), "best_bid_ask")
    elif kind == "last_trade_price" and leg.get("paper_bid") is not None:
        if item.get("side") == "SELL" and float(item["price"]) <= float(leg["paper_bid"]):
            leg["trade_events_at_or_below_bid"] += 1
            if leg.get("first_fill_evidence_at_utc") is None:
                leg["first_fill_evidence_at_utc"] = utc_from_milliseconds(item.get("timestamp"))
                leg["first_fill_evidence_source"] = "last_trade_price"


def summarize_leg_risk(legs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Summarize conservative one-set exposure implied by observed fill evidence."""
    evidenced = [leg for leg in legs.values() if leg["cross_events"] or leg["trade_events_at_or_below_bid"]]
    cost = sum(float(leg["paper_bid"]) for leg in legs.values())
    partial_spend = sum(float(leg["paper_bid"]) for leg in evidenced)
    all_evidenced = len(evidenced) == len(legs)
    timestamps = [datetime.fromisoformat(leg["first_fill_evidence_at_utc"].replace("Z", "+00:00")) for leg in evidenced]
    completion_seconds = None
    if all_evidenced and timestamps:
        completion_seconds = round((max(timestamps) - min(timestamps)).total_seconds(), 3)
    return {
        "legs_with_fill_evidence": len(evidenced),
        "all_legs_with_fill_evidence": all_evidenced,
        "complete_set_cost_if_all_fill": round(cost, 8),
        "locked_payoff_if_all_fill": round(1 - cost, 8),
        "worst_case_loss_if_only_evidenced_legs_fill": round(partial_spend, 8) if not all_evidenced else 0.0,
        "first_to_final_leg_evidence_seconds": completion_seconds,
        "status": "ALL_LEGS_EVIDENCED" if all_evidenced else "INCOMPLETE_FILL_EVIDENCE",
    }
