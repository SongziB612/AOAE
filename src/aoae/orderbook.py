"""Minimal public CLOB order-book state for read-only latency research."""

from __future__ import annotations

from typing import Any


def empty_book() -> dict[str, dict[float, float]]:
    return {"bids": {}, "asks": {}}


def apply_book_message(message: dict[str, Any], books: dict[str, dict[str, dict[float, float]]]) -> None:
    kind = message.get("event_type")
    if kind == "book":
        token = str(message.get("asset_id", ""))
        if token not in books:
            return
        books[token] = {
            "bids": {float(level["price"]): float(level["size"]) for level in message.get("bids", []) if float(level["size"]) > 0},
            "asks": {float(level["price"]): float(level["size"]) for level in message.get("asks", []) if float(level["size"]) > 0},
        }
        return
    if kind != "price_change":
        return
    for change in message.get("price_changes", []):
        token = str(change.get("asset_id", ""))
        if token not in books:
            continue
        side = "bids" if str(change.get("side", "")).upper() == "BUY" else "asks"
        price, size = float(change["price"]), float(change["size"])
        if size > 0:
            books[token][side][price] = size
        else:
            books[token][side].pop(price, None)


def top_of_book(book: dict[str, dict[float, float]]) -> dict[str, float | None]:
    bid = max(book["bids"], default=None)
    ask = min(book["asks"], default=None)
    return {
        "bid": bid,
        "bid_size": book["bids"].get(bid) if bid is not None else None,
        "ask": ask,
        "ask_size": book["asks"].get(ask) if ask is not None else None,
    }
