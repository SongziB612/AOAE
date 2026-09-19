"""Integer-lot, cash-defensive simulation for the 10,000 CNY paper account."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from aoae.etf_momentum import MomentumSpec
from aoae.etf_risk_overlay import build_overlay_schedule


def cap_risk_weights(weights: dict[str, float], risk_assets: tuple[str, ...], cap: float) -> dict[str, float]:
    risk_total = sum(weights.get(symbol, 0.0) for symbol in risk_assets)
    scale = min(1.0, cap / risk_total) if risk_total > 0 else 0.0
    return {symbol: weights.get(symbol, 0.0) * scale for symbol in risk_assets}


def order_cost(notional: float, rate: float, minimum: float) -> float:
    return 0.0 if notional == 0 else max(minimum, abs(notional) * rate)


def execution_cost(notional: float, rate: float, minimum: float, slippage_bps: float = 0.0) -> float:
    """Commission plus explicit adverse execution slippage."""
    if slippage_bps < 0:
        raise ValueError("slippage cannot be negative")
    return order_cost(notional, rate, minimum) + abs(notional) * slippage_bps / 10_000


def target_lots(pre_value: float, weights: dict[str, float], prices: pd.Series, lot_size: int) -> dict[str, int]:
    return {
        symbol: int(np.floor(pre_value * weight / float(prices[symbol]) / lot_size) * lot_size)
        for symbol, weight in weights.items()
    }


def simulate_small_account(
    open_price: pd.DataFrame,
    close: pd.DataFrame,
    spec: MomentumSpec,
    start: str,
    end: str,
    initial_cash: float = 10_000,
    risk_cap: float = 0.4,
    lot_size: int = 100,
    cost_rate: float = 0.0015,
    minimum_cost: float = 5.0,
    lookback: int = 63,
    target_vol: float = 0.12,
    slippage_bps: float = 0.0,
) -> tuple[pd.Series, list[dict[str, Any]], dict[str, Any]]:
    schedule = build_overlay_schedule(close, spec, lookback, target_vol)
    dates = close.index[(close.index >= start) & (close.index <= end)]
    quantity = {symbol: 0 for symbol in spec.risk_assets}
    cash = initial_cash
    equity, trades = [], []
    all_buys_valid = True
    minimum_cash = cash
    for date in dates:
        if date in schedule:
            raw_weights, scores, signal_date, diagnostics = schedule[date]
            prices = open_price.loc[date, list(spec.risk_assets)]
            pre_value = cash + sum(quantity[s] * float(prices[s]) for s in spec.risk_assets)
            weights = cap_risk_weights(raw_weights, spec.risk_assets, risk_cap)
            targets = target_lots(pre_value, weights, prices, lot_size)

            deltas = {symbol: targets[symbol] - quantity[symbol] for symbol in spec.risk_assets}
            total_cost = sum(execution_cost(deltas[s] * float(prices[s]), cost_rate, minimum_cost, slippage_bps) for s in spec.risk_assets)
            cash_after = cash - sum(deltas[s] * float(prices[s]) for s in spec.risk_assets) - total_cost
            while cash_after < -1e-9:
                reducible = [s for s in spec.risk_assets if deltas[s] > 0]
                if not reducible:
                    raise ValueError("negative cash cannot be resolved by reducing buys")
                symbol = min(reducible, key=lambda s: (scores[s], s))
                targets[symbol] -= lot_size
                deltas = {s: targets[s] - quantity[s] for s in spec.risk_assets}
                total_cost = sum(execution_cost(deltas[s] * float(prices[s]), cost_rate, minimum_cost, slippage_bps) for s in spec.risk_assets)
                cash_after = cash - sum(deltas[s] * float(prices[s]) for s in spec.risk_assets) - total_cost

            legs = []
            for symbol, delta in deltas.items():
                if delta:
                    all_buys_valid &= delta < 0 or delta % lot_size == 0
                    notional = delta * float(prices[symbol])
                    legs.append({
                        "symbol": symbol,
                        "side": "BUY" if delta > 0 else "SELL",
                        "quantity": abs(delta),
                        "price": round(float(prices[symbol]), 6),
                        "notional_cny": round(abs(notional), 2),
                        "cost_cny": round(execution_cost(notional, cost_rate, minimum_cost, slippage_bps), 2),
                    })
            quantity, cash = targets, cash_after
            minimum_cash = min(minimum_cash, cash)
            trades.append({
                "signal_date": signal_date,
                "execution_date": date.date().isoformat(),
                "risk_exposure_before_lot_rounding": round(sum(weights.values()), 8),
                "positions_after": {s: q for s, q in quantity.items() if q},
                "cash_after_cny": round(cash, 2),
                "cost_cny": round(total_cost, 2),
                "legs": legs,
                "overlay_diagnostics": {k: round(v, 8) for k, v in diagnostics.items()},
            })
        value = cash + sum(quantity[s] * float(close.at[date, s]) for s in spec.risk_assets)
        equity.append(value)
    diagnostics = {
        "all_buys_are_lot_multiples": all_buys_valid,
        "minimum_cash_cny": round(minimum_cash, 8),
        "cash_never_negative": minimum_cash >= -1e-9,
        "ending_cash_cny": round(cash, 8),
        "ending_positions": {s: q for s, q in quantity.items() if q},
    }
    return pd.Series(equity, index=dates, name="small_account"), trades, diagnostics


def executable_benchmark(open_price: pd.DataFrame, close: pd.DataFrame, symbol: str, start: str, end: str, initial_cash: float, lot_size: int, rate: float, minimum: float) -> pd.Series:
    dates = close.index[(close.index >= start) & (close.index <= end)]
    first = dates[0]
    price = float(open_price.at[first, symbol])
    quantity = int(np.floor(initial_cash / price / lot_size) * lot_size)
    while quantity and quantity * price + order_cost(quantity * price, rate, minimum) > initial_cash:
        quantity -= lot_size
    cash = initial_cash - quantity * price - order_cost(quantity * price, rate, minimum)
    return (cash + close.loc[dates, symbol] * quantity).rename("executable_benchmark")
