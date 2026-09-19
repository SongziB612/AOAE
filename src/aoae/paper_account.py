"""Fail-closed local paper account primitives."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import pandas as pd


def load_paper_spec(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("mode") != "local_broker_independent_simulation":
        raise ValueError("only local simulation is supported")
    if any(raw.get(key) is not False for key in ("orders_authorized", "capital_authorized", "broker_connection_authorized")):
        raise ValueError("paper account must prohibit orders, capital, and broker connections")
    if raw["broker"] is not None:
        raise ValueError("local paper account cannot name a live broker")
    if raw["execution"]["fractional_shares_forbidden"] is not True:
        raise ValueError("small account must forbid fractional shares")
    if raw["risk_limits"]["pause_new_risk_at_equity_cny"] >= raw["initial_cash_cny"]:
        raise ValueError("pause equity must be below initial cash")
    return raw


def initialize_account(spec_path: Path) -> dict[str, Any]:
    spec = load_paper_spec(spec_path)
    initial = float(spec["initial_cash_cny"])
    return {
        "schema_version": 1,
        "account_id": spec["account_id"],
        "mode": spec["mode"],
        "spec_sha256": sha256(spec_path.read_bytes()).hexdigest(),
        "as_of": spec["inception_date"],
        "status": "ACTIVE_WAITING_FOR_FIRST_ELIGIBLE_SIGNAL",
        "cash_cny": initial,
        "positions": {},
        "market_value_cny": 0.0,
        "equity_cny": initial,
        "realized_pnl_cny": 0.0,
        "unrealized_pnl_cny": 0.0,
        "drawdown_fraction": 0.0,
        "risk_budget": {
            "maximum_acceptable_loss_cny": spec["risk_limits"]["maximum_acceptable_loss_cny"],
            "pause_new_risk_at_loss_cny": spec["risk_limits"]["pause_new_risk_at_loss_cny"],
            "remaining_to_pause_cny": spec["risk_limits"]["pause_new_risk_at_loss_cny"],
            "remaining_to_maximum_acceptable_loss_cny": spec["risk_limits"]["maximum_acceptable_loss_cny"],
        },
        "execution_constraints": {
            "buy_lot_size_shares": spec["execution"]["buy_lot_size_shares"],
            "maximum_risk_asset_market_value_cny": round(initial * spec["execution"]["maximum_risk_asset_market_value_fraction"], 2),
            "defensive_asset": "cash",
            "minimum_cost_per_order_cny": spec["cost_model"]["minimum_cost_per_order_cny"],
        },
        "next_event": (
            f"wait for first common {'daily' if spec['execution']['signal'] == 'every_common_trading_day_close' else 'calendar-month-end'} "
            f"close strictly after {spec['inception_date']}; create paper order for next common open"
        ),
        "events": [{
            "date": spec["inception_date"],
            "type": "ACCOUNT_OPENED",
            "cash_change_cny": initial,
            "note": "local simulation only; no broker, position, order, or real capital",
        }],
        "orders_authorized": False,
        "capital_authorized": False,
        "broker_connection_authorized": False,
    }


def validate_order_draft(spec: dict[str, Any], signal_date: str, execution_date: str, legs: list[dict[str, float]]) -> dict[str, float]:
    signal = pd.Timestamp(signal_date)
    execution = pd.Timestamp(execution_date)
    if signal <= pd.Timestamp(spec["inception_date"]):
        raise ValueError("stale or backfilled signal")
    if execution <= signal:
        raise ValueError("execution must occur after signal")
    lot = int(spec["execution"]["buy_lot_size_shares"])
    total_notional = 0.0
    total_cost = 0.0
    for leg in legs:
        quantity, price = int(leg["quantity"]), float(leg["price"])
        if quantity <= 0 or quantity % lot:
            raise ValueError("order quantity violates lot size")
        if price <= 0:
            raise ValueError("order price must be positive")
        notional = quantity * price
        total_notional += notional
        total_cost += max(float(spec["cost_model"]["minimum_cost_per_order_cny"]), notional * float(spec["cost_model"]["one_way_rate"]))
    cap = float(spec["initial_cash_cny"]) * float(spec["execution"]["maximum_risk_asset_market_value_fraction"])
    if total_notional > cap + 1e-9:
        raise ValueError("draft exceeds risk-asset market-value cap")
    if total_notional + total_cost > float(spec["initial_cash_cny"]):
        raise ValueError("draft exceeds available starting cash")
    return {"total_notional_cny": round(total_notional, 2), "estimated_cost_cny": round(total_cost, 2)}
