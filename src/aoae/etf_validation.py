"""Independent VectorBT accounting and stability checks for the ETF champion."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import vectorbt as vbt

from aoae.etf_momentum import MomentumSpec, load_spec


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def load_validation(validation_path: Path, repo_root: Path) -> tuple[dict[str, Any], MomentumSpec, dict[str, Any]]:
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    frozen = validation["frozen_inputs"]
    strategy_spec_path = repo_root / frozen["strategy_spec_path"]
    strategy_result_path = repo_root / frozen["strategy_result_path"]
    if _digest(strategy_spec_path) != frozen["strategy_spec_sha256"]:
        raise ValueError("strategy specification changed after validation preregistration")
    if _digest(strategy_result_path) != frozen["strategy_result_sha256"]:
        raise ValueError("strategy result changed after validation preregistration")
    if validation["external_engine"]["commit"] != "34b6d5935e3ea3eccd549e2592bc0f455b8045f5":
        raise ValueError("unexpected VectorBT commit")
    return validation, load_spec(strategy_spec_path), json.loads(strategy_result_path.read_text(encoding="utf-8"))


def load_panels(data_dir: Path, spec: MomentumSpec, expected_hashes: dict[str, str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    opens, closes = {}, {}
    for symbol in spec.symbols:
        path = data_dir / f"{symbol}.csv"
        if _digest(path) != expected_hashes[symbol]:
            raise ValueError(f"price hash changed: {symbol}")
        frame = pd.read_csv(path, parse_dates=["date"]).sort_values("date").set_index("date")
        opens[symbol], closes[symbol] = frame["open"], frame["close"]
    open_price = pd.concat(opens, axis=1, join="inner").sort_index()
    close = pd.concat(closes, axis=1, join="inner").sort_index()
    dates = open_price.index.intersection(close.index)
    return open_price.loc[dates], close.loc[dates]


def independent_targets(close: pd.DataFrame, spec: MomentumSpec) -> pd.DataFrame:
    targets = pd.DataFrame(np.nan, index=close.index, columns=close.columns)
    month_ends = close.groupby(close.index.to_period("M")).tail(1).index
    index_number = {date: i for i, date in enumerate(close.index)}
    for signal_date in month_ends:
        i = index_number[signal_date]
        if i < max(spec.windows) or i + 1 == len(close):
            continue
        endpoint = close.iloc[i - spec.skip]
        scores = {}
        for symbol in spec.risk_assets:
            components = [float(endpoint[symbol] / close.iloc[i - window][symbol] - 1) for window in spec.windows]
            scores[symbol] = sum(components) / len(components)
        selected = sorted((s for s in spec.risk_assets if scores[s] > 0), key=lambda s: (-scores[s], s))[:spec.top_n]
        weights = {symbol: 0.0 for symbol in spec.symbols}
        for symbol in selected:
            weights[symbol] = 1 / spec.top_n
        weights[spec.defensive_asset] = 1 - sum(weights.values())
        targets.loc[close.index[i + 1]] = pd.Series(weights)
    return targets


def vectorbt_equity(open_price: pd.DataFrame, close: pd.DataFrame, spec: MomentumSpec) -> pd.Series:
    portfolio = vbt.Portfolio.from_orders(
        close=close,
        size=independent_targets(close, spec),
        size_type="targetpercent",
        price=open_price,
        val_price=open_price,
        fees=spec.cost_rate,
        init_cash=spec.initial_capital,
        cash_sharing=True,
        group_by=True,
        call_seq="auto",
        update_value=True,
        freq="1D",
    )
    value = portfolio.value(group_by=True)
    if isinstance(value, pd.DataFrame):
        value = value.iloc[:, 0]
    return value.rename("vectorbt_strategy")


def benchmark_equity(open_price: pd.DataFrame, close: pd.DataFrame, spec: MomentumSpec) -> pd.Series:
    first = close.index[0]
    units = spec.initial_capital * (1 - spec.cost_rate) / float(open_price.at[first, spec.benchmark])
    return (close[spec.benchmark] * units).rename("benchmark")


def period_stats(equity: pd.Series, baseline: float | None = None, start_date: str | None = None) -> dict[str, float | str | int]:
    baseline = float(equity.iloc[0]) if baseline is None else baseline
    normalized = equity / baseline
    peak = normalized.cummax()
    start = equity.index[0] if start_date is None else pd.Timestamp(start_date)
    years = (equity.index[-1] - start).days / 365.25
    return {
        "start": start.date().isoformat(),
        "end": equity.index[-1].date().isoformat(),
        "observations": len(equity),
        "total_return": round(float(normalized.iloc[-1] - 1), 8),
        "cagr": round(float(normalized.iloc[-1] ** (1 / years) - 1), 8),
        "max_drawdown": round(float((normalized / peak - 1).min()), 8),
    }


def run_validation(validation_path: Path, repo_root: Path, data_dir: Path) -> dict[str, Any]:
    validation, spec, champion = load_validation(validation_path, repo_root)
    open_price, close = load_panels(data_dir, spec, champion["inputs"]["price_sha256"])
    strategy = vectorbt_equity(open_price, close, spec)
    benchmark = benchmark_equity(open_price, close, spec)
    holdout_mask = (close.index >= spec.holdout_start) & (close.index <= spec.holdout_end)
    prior = close.index[close.index < spec.holdout_start][-1]
    strategy_holdout, benchmark_holdout = strategy.loc[holdout_mask], benchmark.loc[holdout_mask]
    external = period_stats(strategy_holdout, float(strategy.at[prior]), spec.holdout_start)
    external_benchmark = period_stats(benchmark_holdout, float(benchmark.at[prior]), spec.holdout_start)
    original = champion["holdout"]["strategy"]
    reproduction_rule = validation["tests"]["full_holdout_reproduction"]
    reproduction = {
        "vectorbt": external,
        "original": original,
        "absolute_total_return_difference": round(abs(external["total_return"] - original["total_return"]), 8),
        "absolute_max_drawdown_difference": round(abs(external["max_drawdown"] - original["max_drawdown"]), 8),
    }

    rolling_rule = validation["tests"]["rolling_windows"]
    length, step = rolling_rule["length_common_observations"], rolling_rule["step_common_observations"]
    rolling = []
    for start_i in range(0, len(strategy_holdout) - length + 1, step):
        end_i = start_i + length
        ss, bb = strategy_holdout.iloc[start_i:end_i], benchmark_holdout.iloc[start_i:end_i]
        sm, bm = period_stats(ss), period_stats(bb)
        rolling.append({"strategy": sm, "benchmark": bm, "positive": sm["total_return"] > 0, "beats_benchmark": sm["total_return"] > bm["total_return"], "lower_drawdown": sm["max_drawdown"] > bm["max_drawdown"]})

    loo_rule = validation["tests"]["leave_one_risk_asset_out"]
    leave_one_out = []
    for omitted in loo_rule["assets"]:
        variant = replace(spec, risk_assets=tuple(s for s in spec.risk_assets if s != omitted))
        equity = vectorbt_equity(open_price, close, variant)
        vm = period_stats(equity.loc[holdout_mask], float(equity.at[prior]), spec.holdout_start)
        leave_one_out.append({"omitted": omitted, "metrics": vm, "positive": vm["cagr"] > 0, "beats_benchmark": vm["cagr"] > external_benchmark["cagr"], "above_drawdown_floor": vm["max_drawdown"] >= loo_rule["drawdown_floor"]})

    fraction = lambda key: sum(bool(row[key]) for row in rolling) / len(rolling)
    checks = {
        "external_total_return_reproduces": reproduction["absolute_total_return_difference"] <= reproduction_rule["maximum_total_return_difference"],
        "external_drawdown_reproduces": reproduction["absolute_max_drawdown_difference"] <= reproduction_rule["maximum_max_drawdown_difference"],
        "rolling_positive_fraction": fraction("positive") >= rolling_rule["minimum_fraction_positive_return"],
        "rolling_beats_benchmark_fraction": fraction("beats_benchmark") >= rolling_rule["minimum_fraction_beating_benchmark_return"],
        "rolling_lower_drawdown_fraction": fraction("lower_drawdown") >= rolling_rule["minimum_fraction_lower_drawdown_than_benchmark"],
        "loo_positive_count": sum(row["positive"] for row in leave_one_out) >= loo_rule["minimum_variants_with_positive_cagr"],
        "loo_beats_benchmark_count": sum(row["beats_benchmark"] for row in leave_one_out) >= loo_rule["minimum_variants_beating_benchmark_cagr"],
        "loo_drawdown_floor": all(row["above_drawdown_floor"] for row in leave_one_out),
    }
    return {
        "schema_version": 1,
        "validation_id": validation["validation_id"],
        "engine": {"name": "vectorbt", "version": vbt.__version__, "commit": validation["external_engine"]["commit"], "plotly_compatibility_pin": "6.5.0"},
        "full_holdout_reproduction": reproduction,
        "benchmark": external_benchmark,
        "rolling_windows": {"count": len(rolling), "positive_fraction": round(fraction("positive"), 6), "beats_benchmark_fraction": round(fraction("beats_benchmark"), 6), "lower_drawdown_fraction": round(fraction("lower_drawdown"), 6), "windows": rolling},
        "leave_one_risk_asset_out": leave_one_out,
        "checks": checks,
        "result": {"status": "PASS" if all(checks.values()) else "FAIL", "decision": validation["next_step_if_pass"] if all(checks.values()) else validation["next_step_if_fail"]},
        "orders_authorized": False,
        "capital_authorized": False,
    }
