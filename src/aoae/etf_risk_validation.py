"""Independent VectorBT stability audit for the ETF volatility overlay."""

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
from aoae.etf_validation import benchmark_equity, load_panels, period_stats, vectorbt_equity


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def independent_overlay_targets(close: pd.DataFrame, spec: MomentumSpec, lookback: int, target_vol: float) -> pd.DataFrame:
    """Reimplement the frozen overlay without importing its production weight function."""
    targets = pd.DataFrame(np.nan, index=close.index, columns=close.columns)
    month_ends = close.groupby(close.index.to_period("M")).tail(1).index
    locations = {date: i for i, date in enumerate(close.index)}
    for signal_date in month_ends:
        i = locations[signal_date]
        if i < max(max(spec.windows), lookback) or i + 1 >= len(close):
            continue
        endpoint = close.iloc[i - spec.skip]
        scores = {
            symbol: float(np.mean([endpoint[symbol] / close.iloc[i - window][symbol] - 1 for window in spec.windows]))
            for symbol in spec.risk_assets
        }
        selected = sorted((s for s in spec.risk_assets if scores[s] > 0), key=lambda s: (-scores[s], s))[:spec.top_n]
        weights = {symbol: 0.0 for symbol in spec.symbols}
        if selected:
            returns = close[selected].iloc[i - lookback : i + 1].pct_change().dropna()
            annual_vol = returns.std(ddof=1) * np.sqrt(252)
            inv = 1 / annual_vol
            selected_weights = inv / inv.sum()
            covariance = returns.cov().to_numpy() * 252
            vector = selected_weights.to_numpy()
            full_vol = float(np.sqrt(max(float(vector @ covariance @ vector), 0.0)))
            exposure = min(len(selected) / spec.top_n, target_vol / full_vol, 1.0)
            for symbol in selected:
                weights[symbol] = float(selected_weights[symbol] * exposure)
            weights[spec.defensive_asset] = 1 - exposure
        else:
            weights[spec.defensive_asset] = 1.0
        targets.loc[close.index[i + 1]] = pd.Series(weights)
    return targets


def overlay_equity(open_price: pd.DataFrame, close: pd.DataFrame, spec: MomentumSpec, lookback: int, target_vol: float) -> pd.Series:
    portfolio = vbt.Portfolio.from_orders(
        close=close,
        size=independent_overlay_targets(close, spec, lookback, target_vol),
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
    return (value.iloc[:, 0] if isinstance(value, pd.DataFrame) else value).rename("overlay")


def run_validation(validation_path: Path, repo_root: Path, data_dir: Path) -> dict[str, Any]:
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    frozen = validation["frozen_inputs"]
    overlay_spec_path = repo_root / frozen["overlay_spec_path"]
    overlay_result_path = repo_root / frozen["overlay_result_path"]
    if digest(overlay_spec_path) != frozen["overlay_spec_sha256"] or digest(overlay_result_path) != frozen["overlay_result_sha256"]:
        raise ValueError("frozen overlay inputs changed")
    overlay_spec = json.loads(overlay_spec_path.read_text(encoding="utf-8"))
    recorded = json.loads(overlay_result_path.read_text(encoding="utf-8"))
    base_spec = load_spec(repo_root / overlay_spec["base_signal"]["spec_path"])
    open_price, close = load_panels(data_dir, base_spec, recorded["inputs"]["price_sha256"])
    risk = overlay_spec["risk_overlay"]
    lookback, target_vol = int(risk["daily_return_lookback"]), float(risk["target_annualized_volatility"])
    start, end = overlay_spec["diagnostic_period"]
    mask = (close.index >= start) & (close.index <= end)
    prior = close.index[close.index < start][-1]

    overlay = overlay_equity(open_price, close, base_spec, lookback, target_vol)
    champion = vectorbt_equity(open_price, close, base_spec)
    benchmark = benchmark_equity(open_price, close, base_spec)
    om = period_stats(overlay.loc[mask], float(overlay.at[prior]), start)
    cm = period_stats(champion.loc[mask], float(champion.at[prior]), start)
    bm = period_stats(benchmark.loc[mask], float(benchmark.at[prior]), start)
    original = recorded["diagnostic"]["risk_overlay"]
    reproduction = {
        "vectorbt": om,
        "original": original,
        "absolute_total_return_difference": round(abs(om["total_return"] - original["total_return"]), 8),
        "absolute_max_drawdown_difference": round(abs(om["max_drawdown"] - original["max_drawdown"]), 8),
    }

    rolling_rule = validation["tests"]["rolling_windows"]
    length, step = rolling_rule["length_common_observations"], rolling_rule["step_common_observations"]
    oh, ch = overlay.loc[mask], champion.loc[mask]
    rolling = []
    for start_i in range(0, len(oh) - length + 1, step):
        os, cs = period_stats(oh.iloc[start_i : start_i + length]), period_stats(ch.iloc[start_i : start_i + length])
        rolling.append({
            "overlay": os, "champion": cs,
            "positive": os["total_return"] > 0,
            "beats_champion": os["total_return"] > cs["total_return"],
            "lower_drawdown": os["max_drawdown"] > cs["max_drawdown"],
        })

    stress_rule = validation["tests"]["cost_stress"]
    stress_spec = replace(base_spec, cost_rate=float(stress_rule["one_way_cost_bps"]) / 10_000)
    stressed = overlay_equity(open_price, close, stress_spec, lookback, target_vol)
    stress_metrics = period_stats(stressed.loc[mask], float(stressed.at[prior]), start)

    loo_rule = validation["tests"]["leave_one_risk_asset_out"]
    leave_one_out = []
    for omitted in loo_rule["assets"]:
        variant = replace(base_spec, risk_assets=tuple(s for s in base_spec.risk_assets if s != omitted))
        variant_equity = overlay_equity(open_price, close, variant, lookback, target_vol)
        vm = period_stats(variant_equity.loc[mask], float(variant_equity.at[prior]), start)
        leave_one_out.append({
            "omitted": omitted, "metrics": vm,
            "positive": vm["cagr"] > 0,
            "beats_benchmark": vm["cagr"] > bm["cagr"],
            "above_drawdown_floor": vm["max_drawdown"] >= loo_rule["drawdown_floor"],
        })

    fraction = lambda key: sum(bool(row[key]) for row in rolling) / len(rolling)
    reproduction_rule = validation["tests"]["full_period_reproduction"]
    checks = {
        "external_total_return_reproduces": reproduction["absolute_total_return_difference"] <= reproduction_rule["maximum_total_return_difference"],
        "external_drawdown_reproduces": reproduction["absolute_max_drawdown_difference"] <= reproduction_rule["maximum_max_drawdown_difference"],
        "rolling_positive_fraction": fraction("positive") >= rolling_rule["minimum_fraction_positive_return"],
        "rolling_beats_champion_fraction": fraction("beats_champion") >= rolling_rule["minimum_fraction_beating_champion_return"],
        "rolling_lower_drawdown_fraction": fraction("lower_drawdown") >= rolling_rule["minimum_fraction_lower_drawdown_than_champion"],
        "cost_stress_cagr": stress_metrics["cagr"] >= stress_rule["minimum_cagr"],
        "cost_stress_drawdown": stress_metrics["max_drawdown"] >= stress_rule["drawdown_floor"],
        "loo_positive_count": sum(x["positive"] for x in leave_one_out) >= loo_rule["minimum_variants_with_positive_cagr"],
        "loo_beats_benchmark_count": sum(x["beats_benchmark"] for x in leave_one_out) >= loo_rule["minimum_variants_beating_benchmark_cagr"],
        "loo_drawdown_floor": all(x["above_drawdown_floor"] for x in leave_one_out),
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    return {
        "schema_version": 1,
        "validation_id": validation["validation_id"],
        "engine": {"name": "vectorbt", "version": vbt.__version__, "commit": validation["external_engine"]["commit"]},
        "full_period_reproduction": reproduction,
        "champion": cm,
        "benchmark": bm,
        "rolling_windows": {
            "count": len(rolling),
            "positive_fraction": round(fraction("positive"), 6),
            "beats_champion_fraction": round(fraction("beats_champion"), 6),
            "lower_drawdown_fraction": round(fraction("lower_drawdown"), 6),
            "windows": rolling,
        },
        "cost_stress": {"one_way_cost_bps": stress_rule["one_way_cost_bps"], "metrics": stress_metrics},
        "leave_one_risk_asset_out": leave_one_out,
        "checks": checks,
        "result": {"status": status, "decision": validation["next_step_if_pass"] if status == "PASS" else validation["next_step_if_fail"]},
        "orders_authorized": False,
        "capital_authorized": False,
    }
