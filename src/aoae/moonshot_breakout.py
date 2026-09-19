"""Fixed long-only ETF breakout simulation for a bounded experimental sleeve."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from aoae.small_account import order_cost


def simulate_breakout(
    opens: pd.DataFrame,
    closes: pd.DataFrame,
    start: str,
    end: str,
    initial_cash: float = 3_000,
    entry_window: int = 55,
    exit_window: int = 20,
    rank_window: int = 63,
    lot_size: int = 100,
    commission_rate: float = 0.0015,
    minimum_commission: float = 5,
    slippage_bps: float = 10,
) -> tuple[pd.Series, list[dict[str, Any]], list[dict[str, Any]]]:
    """Signal at close and execute at the next common open without leverage."""
    if not opens.index.equals(closes.index) or not opens.columns.equals(closes.columns):
        raise ValueError("open and close panels differ")
    if min(entry_window, exit_window, rank_window, lot_size) <= 0:
        raise ValueError("windows and lot size must be positive")
    dates = closes.index[(closes.index >= start) & (closes.index <= end)]
    if not len(dates):
        raise ValueError("empty qualification period")
    cash = float(initial_cash)
    symbol: str | None = None
    quantity = 0
    entry_total = 0.0
    entry_date: str | None = None
    equity_values: list[float] = []
    events: list[dict[str, Any]] = []
    closed: list[dict[str, Any]] = []
    slip = float(slippage_bps) / 10_000

    for date in dates:
        location = closes.index.get_loc(date)
        signal_i = location - 1
        if signal_i >= max(entry_window, exit_window, rank_window):
            signal_date = closes.index[signal_i]
            if symbol is not None:
                exit_floor = float(closes[symbol].iloc[signal_i - exit_window : signal_i].min())
                if float(closes.at[signal_date, symbol]) < exit_floor:
                    price = float(opens.at[date, symbol]) * (1 - slip)
                    proceeds = quantity * price
                    cost = order_cost(proceeds, commission_rate, minimum_commission)
                    cash += proceeds - cost
                    pnl = proceeds - cost - entry_total
                    event = {
                        "type": "EXIT",
                        "signal_date": signal_date.date().isoformat(),
                        "execution_date": date.date().isoformat(),
                        "symbol": symbol,
                        "quantity": quantity,
                        "price_after_slippage": round(price, 6),
                        "cost_cny": round(cost, 2),
                        "trade_net_pnl_cny": round(pnl, 2),
                    }
                    events.append(event)
                    closed.append(event)
                    symbol, quantity, entry_total, entry_date = None, 0, 0.0, None
            else:
                candidates = []
                for candidate in closes.columns:
                    prior_high = float(closes[candidate].iloc[signal_i - entry_window : signal_i].max())
                    current = float(closes.at[signal_date, candidate])
                    momentum = current / float(closes[candidate].iloc[signal_i - rank_window]) - 1
                    if current > prior_high:
                        candidates.append((momentum, candidate))
                if candidates:
                    _, selected = max(candidates, key=lambda item: (item[0], -int(item[1])))
                    price = float(opens.at[date, selected]) * (1 + slip)
                    target = int(np.floor(cash / price / lot_size) * lot_size)
                    while target > 0:
                        notional = target * price
                        cost = order_cost(notional, commission_rate, minimum_commission)
                        if notional + cost <= cash + 1e-9:
                            break
                        target -= lot_size
                    if target > 0:
                        notional = target * price
                        cost = order_cost(notional, commission_rate, minimum_commission)
                        cash -= notional + cost
                        symbol, quantity = selected, target
                        entry_total = notional + cost
                        entry_date = date.date().isoformat()
                        events.append({
                            "type": "ENTRY",
                            "signal_date": signal_date.date().isoformat(),
                            "execution_date": entry_date,
                            "symbol": symbol,
                            "quantity": quantity,
                            "price_after_slippage": round(price, 6),
                            "cost_cny": round(cost, 2),
                        })
        value = cash + (quantity * float(closes.at[date, symbol]) if symbol is not None else 0.0)
        equity_values.append(value)
    return pd.Series(equity_values, index=dates, name="moonshot_breakout"), events, closed


def executable_buy_hold(
    opens: pd.DataFrame,
    closes: pd.DataFrame,
    symbol: str,
    start: str,
    end: str,
    initial_cash: float,
    lot_size: int,
    commission_rate: float,
    minimum_commission: float,
    slippage_bps: float,
) -> pd.Series:
    dates = closes.index[(closes.index >= start) & (closes.index <= end)]
    price = float(opens.at[dates[0], symbol]) * (1 + slippage_bps / 10_000)
    quantity = int(np.floor(initial_cash / price / lot_size) * lot_size)
    while quantity and quantity * price + order_cost(quantity * price, commission_rate, minimum_commission) > initial_cash:
        quantity -= lot_size
    cash = initial_cash - quantity * price - order_cost(quantity * price, commission_rate, minimum_commission)
    return (cash + quantity * closes.loc[dates, symbol]).rename("buy_hold")
