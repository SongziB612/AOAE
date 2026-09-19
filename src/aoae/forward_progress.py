"""Summarize immutable daily paper snapshots into a current progress view."""

from __future__ import annotations

from datetime import date
from typing import Any


def summarize_forward_progress(
    snapshots: list[dict[str, Any]],
    evaluation_start: str,
    review_date: str,
    initial_equity_cny: float,
) -> dict[str, Any]:
    ordered = sorted(snapshots, key=lambda row: row["as_of"])
    eligible = [row for row in ordered if row["as_of"] >= evaluation_start]
    latest = eligible[-1] if eligible else None
    rebalances = [
        event
        for row in eligible
        for event in row.get("events", [])
        if event.get("type") == "PAPER_MONTHLY_REBALANCE"
    ]
    unique_rebalances = {(event["signal_date"], event["date"]): event for event in rebalances}
    latest_date = latest["as_of"] if latest else evaluation_start
    elapsed = max(0, (date.fromisoformat(latest_date) - date.fromisoformat(evaluation_start)).days)
    equity = float(latest["equity_cny"]) if latest else float(initial_equity_cny)
    drawdowns = [float(row.get("drawdown_fraction", 0.0)) for row in eligible]
    review_elapsed = latest_date >= review_date
    return {
        "as_of": latest_date,
        "elapsed_calendar_days": elapsed,
        "processed_new_market_days": sum(int(row.get("last_run", {}).get("processed_market_days", 0)) for row in eligible),
        "generated_rebalances": len(unique_rebalances),
        "first_eligible_signal": (
            min(unique_rebalances)[0] if unique_rebalances else "PENDING_FIRST_COMMON_MONTH_END"
        ),
        "first_order_lot_feasible": (
            all(int(leg["quantity"]) % 100 == 0 for leg in next(iter(unique_rebalances.values()))["legs"])
            if unique_rebalances else None
        ),
        "current_equity_cny": round(equity, 2),
        "net_pnl_cny": round(equity - initial_equity_cny, 2),
        "maximum_drawdown_fraction": min(drawdowns, default=0.0),
        "latest_account_status": latest.get("status") if latest else "ACTIVE_WAITING_FOR_FIRST_ELIGIBLE_SIGNAL",
        "review_date_elapsed": review_elapsed,
        "status": "READY_FOR_SCHEDULED_REVIEW" if review_elapsed else "ACTIVE_WAITING_FOR_FORWARD_TIME",
    }
