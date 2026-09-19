"""Executable-price arithmetic for mutually exclusive event baskets."""

from __future__ import annotations

from typing import Any, Sequence


def evaluate_complete_set(books: Sequence[dict[str, Any]], fee_rates: Sequence[float]) -> dict[str, Any]:
    if len(books) < 2 or len(books) != len(fee_rates):
        raise ValueError("a complete set needs at least two books and one fee rate per book")
    asks: list[float] = []
    bids: list[float] = []
    ask_sizes: list[float] = []
    for book in books:
        ask_levels = [(float(level["price"]), float(level["size"])) for level in book.get("asks", [])]
        bid_levels = [(float(level["price"]), float(level["size"])) for level in book.get("bids", [])]
        if not ask_levels or not bid_levels:
            raise ValueError("every leg needs a two-sided order book")
        best_ask = min(price for price, _ in ask_levels)
        best_bid = max(price for price, _ in bid_levels)
        if not 0 < best_bid < best_ask < 1:
            raise ValueError("book prices must satisfy 0 < best bid < best ask < 1")
        asks.append(best_ask)
        bids.append(best_bid)
        ask_sizes.append(sum(size for price, size in ask_levels if price == best_ask))
    if any(isinstance(rate, bool) or not 0 <= rate <= 1 for rate in fee_rates):
        raise ValueError("fee rates must be in [0, 1]")
    taker_fee = sum(rate * price * (1 - price) for rate, price in zip(fee_rates, asks, strict=True))
    taker_cost = sum(asks) + taker_fee
    maker_cost = sum(bids)
    return {
        "leg_count": len(books),
        "taker": {
            "complete_set_cost": round(taker_cost, 8),
            "net_payoff": round(1 - taker_cost, 8),
            "profitable_before_external_costs": taker_cost < 1,
            "displayed_capacity_sets": round(min(ask_sizes), 8),
        },
        "maker": {
            "complete_set_bid_cost": round(maker_cost, 8),
            "payoff_if_every_leg_fills": round(1 - maker_cost, 8),
            "all_legs_fill_guaranteed": False,
        },
        "best_asks": asks,
        "best_bids": bids,
    }
