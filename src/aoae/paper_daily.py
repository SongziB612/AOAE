"""Daily local-only roll-forward for the small ETF paper account."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pandas as pd

from aoae.etf_momentum import MomentumSpec, load_prices
from aoae.etf_risk_overlay import overlay_weights
from aoae.small_account import cap_risk_weights, order_cost, target_lots


def load_extended_panels(
    frozen_dir: Path,
    update_dir: Path,
    symbols: tuple[str, ...],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    open_price, close, _ = load_prices(frozen_dir, symbols)
    extra_opens, extra_closes = {}, {}
    frozen_end = close.index[-1]
    for symbol in symbols:
        update = pd.read_csv(update_dir / f"{symbol}.csv", parse_dates=["date"]).sort_values("date").set_index("date")
        overlap = update.index.intersection(close.index)
        if overlap.empty or frozen_end not in overlap:
            raise ValueError(f"update lacks frozen-end overlap: {symbol}")
        if abs(float(update.at[frozen_end, "close"]) - float(close.at[frozen_end, symbol])) > 1e-9:
            raise ValueError(f"update is not adjustment-compatible: {symbol}")
        extra = update.loc[update.index > frozen_end]
        extra_opens[symbol], extra_closes[symbol] = extra["open"], extra["close"]
    if extra_opens and len(next(iter(extra_opens.values()))):
        open_price = pd.concat([open_price, pd.concat(extra_opens, axis=1, join="inner")]).sort_index()
        close = pd.concat([close, pd.concat(extra_closes, axis=1, join="inner")]).sort_index()
    if not open_price.index.equals(close.index) or open_price.isna().any().any() or close.isna().any().any():
        raise ValueError("extended common panel is incomplete")
    return open_price, close


def _execute_targets(
    cash: float,
    positions: dict[str, int],
    targets: dict[str, int],
    prices: pd.Series,
    risk_assets: tuple[str, ...],
    rate: float,
    minimum: float,
) -> tuple[float, dict[str, int], list[dict[str, Any]], float]:
    deltas = {s: targets.get(s, 0) - positions.get(s, 0) for s in risk_assets}
    total_cost = sum(order_cost(deltas[s] * float(prices[s]), rate, minimum) for s in risk_assets)
    cash_after = cash - sum(deltas[s] * float(prices[s]) for s in risk_assets) - total_cost
    if cash_after < -1e-9:
        raise ValueError("paper target exceeds cash")
    legs = []
    for symbol, delta in deltas.items():
        if delta:
            notional = delta * float(prices[symbol])
            legs.append({
                "symbol": symbol,
                "side": "BUY" if delta > 0 else "SELL",
                "quantity": abs(delta),
                "paper_fill_open": round(float(prices[symbol]), 6),
                "notional_cny": round(abs(notional), 2),
                "cost_cny": round(order_cost(notional, rate, minimum), 2),
            })
    return cash_after, {s: int(targets.get(s, 0)) for s in risk_assets}, legs, total_cost


def roll_forward(
    state: dict[str, Any],
    account_spec: dict[str, Any],
    strategy_spec: MomentumSpec,
    open_price: pd.DataFrame,
    close: pd.DataFrame,
    as_of: str,
) -> dict[str, Any]:
    result = deepcopy(state)
    prior_as_of = pd.Timestamp(state["as_of"])
    requested = pd.Timestamp(as_of)
    if requested < prior_as_of:
        raise ValueError("cannot roll account backward")
    positions = {s: int(state.get("positions", {}).get(s, {}).get("quantity", 0)) for s in strategy_spec.risk_assets}
    cash = float(state["cash_cny"])
    processed = close.index[(close.index > prior_as_of) & (close.index <= requested)]
    generated_rebalances = 0
    initial = float(account_spec["initial_cash_cny"])
    pause_equity = float(account_spec["risk_limits"]["pause_new_risk_at_equity_cny"])
    lot = int(account_spec["execution"]["buy_lot_size_shares"])
    cap = float(account_spec["execution"]["maximum_risk_asset_market_value_fraction"])
    volatility_lookback = int(account_spec["execution"].get("volatility_lookback_days", 63))
    target_volatility = float(account_spec["execution"].get("target_annualized_volatility", 0.12))
    rate = float(account_spec["cost_model"]["one_way_rate"])
    minimum = float(account_spec["cost_model"]["minimum_cost_per_order_cny"])
    status = state["status"]

    for date in processed:
        i = close.index.get_loc(date)
        if status == "RISK_PAUSE_PENDING_LIQUIDATION":
            targets = {s: 0 for s in strategy_spec.risk_assets}
            cash, positions, legs, cost = _execute_targets(cash, positions, targets, open_price.loc[date], strategy_spec.risk_assets, rate, minimum)
            result["events"].append({"date": date.date().isoformat(), "type": "PAPER_RISK_LIQUIDATION", "legs": legs, "cost_cny": round(cost, 2)})
            status = "PAUSED_AFTER_RISK_LIMIT"
        else:
            prior_is_clean = i > 0 and close.index[i - 1] > pd.Timestamp(account_spec["inception_date"])
            signal_frequency = account_spec["execution"]["signal"]
            is_rebalance = status.startswith("ACTIVE") and prior_is_clean and (
                signal_frequency == "every_common_trading_day_close"
                or (
                    signal_frequency == "last_common_trading_day_of_calendar_month_close"
                    and close.index[i - 1].to_period("M") != date.to_period("M")
                )
            )
            if not is_rebalance:
                equity = cash + sum(positions[s] * float(close.at[date, s]) for s in strategy_spec.risk_assets)
                if status.startswith("ACTIVE") and equity <= pause_equity:
                    status = "RISK_PAUSE_PENDING_LIQUIDATION"
                    result["events"].append({"date": date.date().isoformat(), "type": "RISK_PAUSE_TRIGGERED_AT_CLOSE", "equity_cny": round(equity, 2)})
                continue
            signal_i = i - 1
            raw_weights, scores, diagnostics = overlay_weights(
                close, signal_i, strategy_spec, volatility_lookback, target_volatility
            )
            weights = cap_risk_weights(raw_weights, strategy_spec.risk_assets, cap)
            pre_value = cash + sum(positions[s] * float(open_price.at[date, s]) for s in strategy_spec.risk_assets)
            targets = target_lots(pre_value, weights, open_price.loc[date], lot)
            cash, positions, legs, cost = _execute_targets(cash, positions, targets, open_price.loc[date], strategy_spec.risk_assets, rate, minimum)
            result["events"].append({
                "date": date.date().isoformat(),
                "type": "PAPER_DAILY_REBALANCE" if signal_frequency == "every_common_trading_day_close" else "PAPER_MONTHLY_REBALANCE",
                "signal_date": close.index[signal_i].date().isoformat(), "legs": legs,
                "positions_after": {s: q for s, q in positions.items() if q}, "cash_after_cny": round(cash, 2), "cost_cny": round(cost, 2),
                "scores": {s: round(v, 8) for s, v in scores.items()},
                "risk_exposure_before_lot_rounding": round(sum(weights.values()), 8),
                "overlay_diagnostics": {k: round(v, 8) for k, v in diagnostics.items()},
            })
            generated_rebalances += 1

        equity = cash + sum(positions[s] * float(close.at[date, s]) for s in strategy_spec.risk_assets)
        if status.startswith("ACTIVE") and equity <= pause_equity:
            status = "RISK_PAUSE_PENDING_LIQUIDATION"
            result["events"].append({"date": date.date().isoformat(), "type": "RISK_PAUSE_TRIGGERED_AT_CLOSE", "equity_cny": round(equity, 2)})

    valuation_date = processed[-1] if len(processed) else prior_as_of
    if valuation_date in close.index:
        market_values = {s: positions[s] * float(close.at[valuation_date, s]) for s in strategy_spec.risk_assets if positions[s]}
    else:
        market_values = {}
    market_value = sum(market_values.values())
    equity = cash + market_value
    peak = max([float(state.get("peak_equity_cny", initial)), equity])
    loss = max(0.0, initial - equity)
    result.update({
        "as_of": requested.date().isoformat(),
        "status": status,
        "cash_cny": round(cash, 2),
        "positions": {s: {"quantity": positions[s], "market_value_cny": round(market_values[s], 2)} for s in market_values},
        "market_value_cny": round(market_value, 2),
        "equity_cny": round(equity, 2),
        "unrealized_pnl_cny": round(equity - initial, 2),
        "drawdown_fraction": round(equity / peak - 1, 8),
        "peak_equity_cny": round(peak, 2),
        "risk_budget": {
            "maximum_acceptable_loss_cny": account_spec["risk_limits"]["maximum_acceptable_loss_cny"],
            "pause_new_risk_at_loss_cny": account_spec["risk_limits"]["pause_new_risk_at_loss_cny"],
            "remaining_to_pause_cny": round(float(account_spec["risk_limits"]["pause_new_risk_at_loss_cny"]) - loss, 2),
            "remaining_to_maximum_acceptable_loss_cny": round(float(account_spec["risk_limits"]["maximum_acceptable_loss_cny"]) - loss, 2),
        },
        "last_run": {"requested_as_of": requested.date().isoformat(), "processed_market_days": len(processed), "generated_rebalances": generated_rebalances},
    })
    return result
