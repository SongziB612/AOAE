"""Broker-independent preparation and reconciliation for a manual pilot."""

from __future__ import annotations

from typing import Any


def prepare_manual_packet(snapshot: dict[str, Any], maximum_quote_age_seconds: int = 5) -> dict[str, Any]:
    """Convert the latest clean paper rebalance into a non-executable review packet."""
    events = [event for event in snapshot.get("events", []) if event.get("type") == "PAPER_MONTHLY_REBALANCE"]
    if not events:
        raise ValueError("no clean monthly rebalance exists")
    event = events[-1]
    legs = []
    for leg in event["legs"]:
        quantity = int(leg["quantity"])
        if quantity <= 0 or quantity % 100:
            raise ValueError("paper leg violates 100-share lot")
        legs.append({
            "symbol": str(leg["symbol"]),
            "side": str(leg["side"]),
            "quantity": quantity,
            "paper_reference_price": float(leg["paper_fill_open"]),
            "live_limit_price": None,
        })
    return {
        "account_id": snapshot["account_id"],
        "signal_date": event["signal_date"],
        "paper_execution_date": event["date"],
        "classification": "manual_review_packet_requires_fresh_live_quotes_and_human_approval",
        "maximum_quote_age_seconds": maximum_quote_age_seconds,
        "cancel_unfilled_after_seconds": 60,
        "legs": legs,
        "orders_authorized": False,
        "capital_authorized": False,
    }


def reconcile_manual_fills(packet: dict[str, Any], fills: list[dict[str, Any]]) -> dict[str, Any]:
    """Detect unauthorized, overfilled, or limit-violating manual executions."""
    allowed = {(leg["symbol"], leg["side"]): leg for leg in packet["legs"]}
    totals = {key: 0 for key in allowed}
    violations: list[str] = []
    gross_notional = commission = 0.0
    for fill in fills:
        key = (str(fill["symbol"]), str(fill["side"]))
        if key not in allowed:
            violations.append(f"unauthorized symbol or side: {key[0]} {key[1]}")
            continue
        quantity, price = int(fill["quantity"]), float(fill["price"])
        if quantity <= 0 or price <= 0:
            violations.append(f"invalid fill values: {key[0]}")
            continue
        totals[key] += quantity
        gross_notional += quantity * price
        commission += float(fill.get("commission_cny", 0.0))
        limit = allowed[key].get("live_limit_price")
        if limit is None:
            violations.append(f"missing approved live limit: {key[0]}")
        elif key[1] == "BUY" and price > float(limit) + 1e-9:
            violations.append(f"buy fill above limit: {key[0]}")
        elif key[1] == "SELL" and price < float(limit) - 1e-9:
            violations.append(f"sell fill below limit: {key[0]}")
    for key, quantity in totals.items():
        if quantity > int(allowed[key]["quantity"]):
            violations.append(f"overfill: {key[0]} {key[1]}")
    complete = all(totals[key] == int(allowed[key]["quantity"]) for key in allowed)
    return {
        "status": "VIOLATION" if violations else ("COMPLETE" if complete else "PARTIAL"),
        "filled_quantity": {f"{symbol}:{side}": quantity for (symbol, side), quantity in totals.items()},
        "gross_notional_cny": round(gross_notional, 2),
        "commission_cny": round(commission, 2),
        "violations": violations,
        "automatic_follow_up_allowed": False,
        "capital_authorized": False,
    }
