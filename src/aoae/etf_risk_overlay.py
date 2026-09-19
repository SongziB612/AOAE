"""Pre-registered volatility-control overlay for the ETF momentum champion."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from aoae.etf_momentum import MomentumSpec, score_at, target_weights


def overlay_weights(
    close: pd.DataFrame,
    i: int,
    spec: MomentumSpec,
    lookback: int = 63,
    target_volatility: float = 0.12,
) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    """Apply inverse-volatility weights and a portfolio volatility target at signal index i."""
    if i < max(max(spec.windows), lookback):
        raise ValueError("insufficient lookback")
    scores = score_at(close, i, spec)
    base = target_weights(scores, spec)
    selected = [symbol for symbol in spec.risk_assets if base[symbol] > 0]
    weights = {symbol: 0.0 for symbol in spec.symbols}
    diagnostics: dict[str, float] = {"risk_exposure": 0.0, "estimated_full_risk_volatility": 0.0}
    if not selected:
        weights[spec.defensive_asset] = 1.0
        return weights, scores, diagnostics

    returns = close[selected].iloc[i - lookback : i + 1].pct_change().dropna()
    vol = returns.std(ddof=1) * np.sqrt(252)
    if (vol <= 0).any() or vol.isna().any():
        raise ValueError("non-positive or missing trailing volatility")
    inverse = 1.0 / vol
    normalized = inverse / inverse.sum()
    covariance = returns.cov().to_numpy() * 252
    vector = normalized.to_numpy()
    portfolio_vol = float(np.sqrt(max(float(vector @ covariance @ vector), 0.0)))
    if portfolio_vol <= 0:
        raise ValueError("non-positive selected portfolio volatility")
    base_risk_cap = len(selected) / spec.top_n
    exposure = min(base_risk_cap, target_volatility / portfolio_vol, 1.0)
    for symbol in selected:
        weights[symbol] = float(normalized[symbol] * exposure)
        diagnostics[f"trailing_volatility_{symbol}"] = float(vol[symbol])
    weights[spec.defensive_asset] = 1.0 - exposure
    diagnostics["risk_exposure"] = exposure
    diagnostics["estimated_full_risk_volatility"] = portfolio_vol
    return weights, scores, diagnostics


def build_overlay_schedule(
    close: pd.DataFrame,
    spec: MomentumSpec,
    lookback: int = 63,
    target_volatility: float = 0.12,
) -> dict[pd.Timestamp, tuple[dict[str, float], dict[str, float], str, dict[str, float]]]:
    month_ends = close.groupby(close.index.to_period("M")).tail(1).index
    locations = {date: i for i, date in enumerate(close.index)}
    schedule = {}
    for signal_date in month_ends:
        i = locations[signal_date]
        if i < max(max(spec.windows), lookback) or i + 1 >= len(close):
            continue
        weights, scores, diagnostics = overlay_weights(close, i, spec, lookback, target_volatility)
        schedule[close.index[i + 1]] = (weights, scores, signal_date.date().isoformat(), diagnostics)
    return schedule


def simulate_overlay(
    open_price: pd.DataFrame,
    close: pd.DataFrame,
    spec: MomentumSpec,
    lookback: int = 63,
    target_volatility: float = 0.12,
) -> tuple[pd.Series, list[dict[str, Any]]]:
    schedule = build_overlay_schedule(close, spec, lookback, target_volatility)
    quantity = {symbol: 0.0 for symbol in spec.symbols}
    cash = spec.initial_capital
    equity, trades = [], []
    for date in close.index:
        if date in schedule:
            weights, scores, signal_date, diagnostics = schedule[date]
            pre_value = cash + sum(quantity[s] * float(open_price.at[date, s]) for s in spec.symbols)
            old_notional = {s: quantity[s] * float(open_price.at[date, s]) for s in spec.symbols}
            traded = sum(abs(pre_value * weights[s] - old_notional[s]) for s in spec.symbols)
            cost = traded * spec.cost_rate
            investable = pre_value - cost
            quantity = {s: investable * weights[s] / float(open_price.at[date, s]) for s in spec.symbols}
            cash = 0.0
            trades.append({
                "signal_date": signal_date,
                "execution_date": date.date().isoformat(),
                "weights": {s: round(w, 6) for s, w in weights.items() if w},
                "scores": {s: round(v, 8) for s, v in scores.items()},
                "risk_diagnostics": {k: round(v, 8) for k, v in diagnostics.items()},
                "turnover": round(traded / pre_value, 8),
                "cost_cny": round(cost, 4),
            })
        equity.append(cash + sum(quantity[s] * float(close.at[date, s]) for s in spec.symbols))
    return pd.Series(equity, index=close.index, name="risk_overlay"), trades
