"""Pre-registered monthly dual-momentum ETF backtest."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class MomentumSpec:
    symbols: tuple[str, ...]
    risk_assets: tuple[str, ...]
    defensive_asset: str
    benchmark: str
    windows: tuple[int, int]
    skip: int
    top_n: int
    cost_rate: float
    initial_capital: float
    holdout_start: str
    holdout_end: str


def load_spec(path: Path) -> MomentumSpec:
    raw = json.loads(path.read_text(encoding="utf-8"))
    method, data = raw["method"], raw["data"]
    if raw.get("orders_authorized") is not False or raw.get("capital_authorized") is not False:
        raise ValueError("research specification must not authorize orders or capital")
    if method["execution"] != "next_available_trading_day_open" or method["trial_count"] != 1:
        raise ValueError("unsupported or non-preregistered method")
    symbols = tuple(data["universe"])
    risk_assets = tuple(data["risk_assets"])
    defensive = data["defensive_asset"]
    if set(risk_assets) | {defensive} != set(symbols):
        raise ValueError("universe and allocation assets differ")
    return MomentumSpec(
        symbols=symbols,
        risk_assets=risk_assets,
        defensive_asset=defensive,
        benchmark=data["benchmark"],
        windows=tuple(method["momentum_windows_days"]),
        skip=int(method["skip_recent_days"]),
        top_n=int(method["risk_asset_count"]),
        cost_rate=float(method["one_way_cost_bps"]) / 10_000,
        initial_capital=float(method["initial_capital_cny"]),
        holdout_start=raw["holdout"]["start_date"],
        holdout_end=raw["holdout"]["end_date"],
    )


def load_prices(data_dir: Path, symbols: tuple[str, ...]) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, str]]:
    opens, closes, hashes = {}, {}, {}
    for symbol in symbols:
        path = data_dir / f"{symbol}.csv"
        payload = path.read_bytes()
        hashes[symbol] = sha256(payload).hexdigest()
        frame = pd.read_csv(path, parse_dates=["date"])
        required = {"date", "open", "close"}
        if not required.issubset(frame.columns) or frame["date"].duplicated().any():
            raise ValueError(f"invalid price table: {symbol}")
        frame = frame.sort_values("date").set_index("date")
        if frame[["open", "close"]].isna().any().any() or (frame[["open", "close"]] <= 0).any().any():
            raise ValueError(f"missing or non-positive prices: {symbol}")
        opens[symbol], closes[symbol] = frame["open"], frame["close"]
    open_panel = pd.concat(opens, axis=1, join="inner").sort_index()
    close_panel = pd.concat(closes, axis=1, join="inner").sort_index()
    common = open_panel.index.intersection(close_panel.index)
    if len(common) < max(252, 2) + 2:
        raise ValueError("insufficient common price history")
    return open_panel.loc[common], close_panel.loc[common], hashes


def score_at(close: pd.DataFrame, i: int, spec: MomentumSpec) -> dict[str, float]:
    """Compute only the two pre-registered lagged returns at signal index i."""
    if i < max(spec.windows):
        raise ValueError("insufficient lookback")
    endpoint = close.iloc[i - spec.skip]
    return {
        symbol: float(np.mean([endpoint[symbol] / close.iloc[i - window][symbol] - 1 for window in spec.windows]))
        for symbol in spec.risk_assets
    }


def target_weights(scores: dict[str, float], spec: MomentumSpec) -> dict[str, float]:
    ranked = sorted((symbol for symbol, value in scores.items() if value > 0), key=lambda s: (-scores[s], s))
    selected = ranked[: spec.top_n]
    weights = {symbol: 0.0 for symbol in spec.symbols}
    for symbol in selected:
        weights[symbol] = 1.0 / spec.top_n
    weights[spec.defensive_asset] = 1.0 - sum(weights.values())
    return weights


def build_schedule(close: pd.DataFrame, spec: MomentumSpec) -> dict[pd.Timestamp, tuple[dict[str, float], dict[str, float], str]]:
    month_ends = close.groupby(close.index.to_period("M")).tail(1).index
    locations = {date: i for i, date in enumerate(close.index)}
    schedule = {}
    for signal_date in month_ends:
        i = locations[signal_date]
        if i < max(spec.windows) or i + 1 >= len(close):
            continue
        scores = score_at(close, i, spec)
        schedule[close.index[i + 1]] = (target_weights(scores, spec), scores, signal_date.date().isoformat())
    return schedule


def simulate(open_price: pd.DataFrame, close: pd.DataFrame, spec: MomentumSpec) -> tuple[pd.Series, list[dict[str, Any]], float, float]:
    schedule = build_schedule(close, spec)
    quantity = {symbol: 0.0 for symbol in spec.symbols}
    cash = spec.initial_capital
    equity, trades = [], []
    total_cost = total_turnover = 0.0
    for date in close.index:
        if date in schedule:
            weights, scores, signal_date = schedule[date]
            pre_value = cash + sum(quantity[s] * float(open_price.at[date, s]) for s in spec.symbols)
            old_notional = {s: quantity[s] * float(open_price.at[date, s]) for s in spec.symbols}
            traded = sum(abs(pre_value * weights[s] - old_notional[s]) for s in spec.symbols)
            cost = traded * spec.cost_rate
            investable = pre_value - cost
            quantity = {s: investable * weights[s] / float(open_price.at[date, s]) for s in spec.symbols}
            cash = 0.0
            total_cost += cost
            total_turnover += traded / pre_value
            trades.append({
                "signal_date": signal_date,
                "execution_date": date.date().isoformat(),
                "weights": {s: round(w, 6) for s, w in weights.items() if w},
                "scores": {s: round(v, 8) for s, v in scores.items()},
                "turnover": round(traded / pre_value, 8),
                "cost_cny": round(cost, 4),
            })
        equity.append(cash + sum(quantity[s] * float(close.at[date, s]) for s in spec.symbols))
    return pd.Series(equity, index=close.index, name="strategy"), trades, total_cost, total_turnover


def simulate_benchmark(open_price: pd.DataFrame, close: pd.DataFrame, spec: MomentumSpec) -> pd.Series:
    first = close.index[0]
    capital = spec.initial_capital * (1 - spec.cost_rate)
    quantity = capital / float(open_price.at[first, spec.benchmark])
    return (close[spec.benchmark] * quantity).rename("benchmark")


def metrics(equity: pd.Series, baseline_value: float | None = None, period_start: str | None = None) -> dict[str, float | int | str]:
    equity = equity.dropna()
    baseline = float(equity.iloc[0]) if baseline_value is None else baseline_value
    normalized = equity / baseline
    returns = normalized.pct_change()
    if baseline_value is not None:
        returns.iloc[0] = float(normalized.iloc[0] - 1)
    returns = returns.dropna()
    start = equity.index[0] if period_start is None else pd.Timestamp(period_start)
    years = (equity.index[-1] - start).days / 365.25
    cagr = float(normalized.iloc[-1] ** (1 / years) - 1)
    volatility = float(returns.std(ddof=1) * np.sqrt(252))
    sharpe = float(returns.mean() / returns.std(ddof=1) * np.sqrt(252)) if returns.std(ddof=1) else 0.0
    # An explicitly supplied starting balance is a real high-water mark,
    # even when the first observed close is already below that balance.
    peaks = normalized.cummax()
    if baseline_value is not None:
        peaks = peaks.clip(lower=1.0)
    drawdown = normalized / peaks - 1
    return {
        "start": start.date().isoformat(),
        "first_market_date": equity.index[0].date().isoformat(),
        "end": equity.index[-1].date().isoformat(),
        "observations": len(equity),
        "total_return": round(float(normalized.iloc[-1] - 1), 8),
        "cagr": round(cagr, 8),
        "annualized_volatility": round(volatility, 8),
        "sharpe_zero_rate": round(sharpe, 8),
        "max_drawdown": round(float(drawdown.min()), 8),
    }


def run_backtest(spec_path: Path, data_dir: Path) -> dict[str, Any]:
    spec = load_spec(spec_path)
    open_price, close, hashes = load_prices(data_dir, spec.symbols)
    strategy, trades, total_cost, total_turnover = simulate(open_price, close, spec)
    benchmark = simulate_benchmark(open_price, close, spec)
    mask = (strategy.index >= spec.holdout_start) & (strategy.index <= spec.holdout_end)
    holdout_strategy, holdout_benchmark = strategy.loc[mask], benchmark.loc[mask]
    if holdout_strategy.empty or holdout_strategy.index[-1].date().isoformat() != spec.holdout_end:
        raise ValueError("holdout is incomplete")
    prior = strategy.index[strategy.index < spec.holdout_start][-1]
    sm = metrics(holdout_strategy, float(strategy.at[prior]), spec.holdout_start)
    bm = metrics(holdout_benchmark, float(benchmark.at[prior]), spec.holdout_start)
    checks = {
        "strategy_cagr_above_zero": sm["cagr"] > 0,
        "strategy_cagr_above_benchmark": sm["cagr"] > bm["cagr"],
        "strategy_max_drawdown_less_severe_than_benchmark": sm["max_drawdown"] > bm["max_drawdown"],
        "strategy_sharpe_above_benchmark": sm["sharpe_zero_rate"] > bm["sharpe_zero_rate"],
    }
    holdout_trades = [t for t in trades if spec.holdout_start <= t["execution_date"] <= spec.holdout_end]
    return {
        "schema_version": 1,
        "hypothesis_id": "HYP-0004-cn-etf-dual-momentum",
        "record_type": "preregistered_historical_backtest",
        "inputs": {"price_sha256": hashes, "common_first_date": close.index[0].date().isoformat(), "common_last_date": close.index[-1].date().isoformat(), "common_rows": len(close)},
        "method": {"signal_uses_close_through_signal_date": True, "execution_uses_next_common_day_open": True, "common_calendar_only": True, "fractional_units": True, "one_way_cost_bps": round(spec.cost_rate * 10_000, 4)},
        "holdout": {"strategy": sm, "benchmark": bm, "checks": checks},
        "execution_summary": {"holdout_rebalances": len(holdout_trades), "holdout_turnover": round(sum(t["turnover"] for t in holdout_trades), 8), "holdout_cost_cny": round(sum(t["cost_cny"] for t in holdout_trades), 2), "all_period_rebalances": len(trades), "all_period_turnover": round(total_turnover, 8), "all_period_cost_cny": round(total_cost, 2)},
        "holdout_rebalances": holdout_trades,
        "result": {"status": "PASS" if all(checks.values()) else "FAIL", "decision": "advance_to_independent_data_replication" if all(checks.values()) else "reject_without_holdout_tuning"},
        "orders_authorized": False,
        "capital_authorized": False,
    }
