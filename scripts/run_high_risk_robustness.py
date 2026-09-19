from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

import pandas as pd

from aoae.etf_momentum import load_prices, load_spec, metrics
from aoae.small_account import executable_benchmark, simulate_small_account


def run_window(open_price, close, base_spec, execution, start, end, rate, minimum):
    equity, trades, diagnostics = simulate_small_account(
        open_price,
        close,
        base_spec,
        start,
        end,
        float(execution["initial_cash_cny"]),
        float(execution["risk_asset_market_value_cap_fraction"]),
        int(execution["buy_lot_size_shares"]),
        rate,
        minimum,
        int(execution["volatility_lookback_days"]),
        float(execution["target_annualized_volatility"]),
    )
    benchmark = executable_benchmark(
        open_price,
        close,
        base_spec.benchmark,
        start,
        end,
        float(execution["initial_cash_cny"]),
        int(execution["buy_lot_size_shares"]),
        rate,
        minimum,
    )
    strategy_metrics = metrics(equity, float(execution["initial_cash_cny"]), start)
    benchmark_metrics = metrics(benchmark, float(execution["initial_cash_cny"]), start)
    return {
        "period": [start, end],
        "strategy": strategy_metrics,
        "benchmark": benchmark_metrics,
        "maximum_loss_from_initial_cny": round(max(0.0, float(execution["initial_cash_cny"]) - float(equity.min())), 2),
        "orders": sum(len(item["legs"]) for item in trades),
        "cost_cny": round(sum(item["cost_cny"] for item in trades), 2),
        "cash_never_negative": diagnostics["cash_never_negative"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite: {args.output}")

    raw = json.loads(args.spec.read_text(encoding="utf-8"))
    root = args.repo_root.resolve()
    strategy_spec_path = root / raw["frozen_strategy_spec"]
    strategy_result_path = root / raw["frozen_strategy_result"]
    strategy_spec = json.loads(strategy_spec_path.read_text(encoding="utf-8"))
    strategy_result = json.loads(strategy_result_path.read_text(encoding="utf-8"))
    overlay_spec = json.loads((root / strategy_spec["frozen_inputs"]["overlay_spec_path"]).read_text(encoding="utf-8"))
    base_spec = load_spec(root / overlay_spec["base_signal"]["spec_path"])
    open_price, close, price_hashes = load_prices(root / raw["data_dir"], base_spec.symbols)
    if price_hashes != strategy_result["inputs"]["price_sha256"]:
        raise ValueError("frozen price inputs changed")
    execution = strategy_spec["execution"]

    full_period_cost_stress = []
    for scenario in raw["cost_stress"]:
        row = run_window(
            open_price, close, base_spec, execution, strategy_spec["period"][0], strategy_spec["period"][1],
            float(scenario["one_way_cost_rate"]), float(scenario["minimum_cost_cny"]),
        )
        row["cost_model"] = scenario
        full_period_cost_stress.append(row)

    base_rate = float(raw["cost_stress"][0]["one_way_cost_rate"])
    base_minimum = float(raw["cost_stress"][0]["minimum_cost_cny"])
    calendar = [run_window(open_price, close, base_spec, execution, start, end, base_rate, base_minimum) for start, end in raw["calendar_windows"]]
    rolling = []
    for start in raw["rolling_windows"]["start_dates"]:
        end = (pd.Timestamp(start) + pd.DateOffset(months=int(raw["rolling_windows"]["months"])) - pd.Timedelta(days=1)).date().isoformat()
        rolling.append(run_window(open_price, close, base_spec, execution, start, end, base_rate, base_minimum))

    rule = raw["pass_rule"]
    checks = {
        "all_full_period_cost_scenarios_positive": all(row["strategy"]["total_return"] > 0 for row in full_period_cost_stress),
        "all_full_period_cost_scenarios_within_drawdown_limit": all(row["strategy"]["max_drawdown"] >= float(rule["all_full_period_cost_scenarios_max_drawdown_at_least"]) for row in full_period_cost_stress),
        "minimum_positive_calendar_windows": sum(row["strategy"]["total_return"] > 0 for row in calendar) >= int(rule["minimum_positive_calendar_windows"]),
        "minimum_positive_rolling_windows": sum(row["strategy"]["total_return"] > 0 for row in rolling) >= int(rule["minimum_positive_rolling_windows"]),
        "minimum_rolling_windows_beating_executable_benchmark": sum(row["strategy"]["total_return"] > row["benchmark"]["total_return"] for row in rolling) >= int(rule["minimum_rolling_windows_beating_executable_benchmark"]),
        "maximum_rolling_loss_from_initial_cny": max(row["maximum_loss_from_initial_cny"] for row in rolling) <= float(rule["maximum_rolling_loss_from_initial_cny"]),
        "cash_never_negative": all(row["cash_never_negative"] for row in full_period_cost_stress + calendar + rolling),
    }
    output = {
        "schema_version": 1,
        "hypothesis_id": raw["hypothesis_id"],
        "record_type": "post_discovery_robustness_audit",
        "inputs": {
            "spec_sha256": sha256(args.spec.read_bytes()).hexdigest(),
            "strategy_spec_sha256": sha256(strategy_spec_path.read_bytes()).hexdigest(),
            "strategy_result_sha256": sha256(strategy_result_path.read_bytes()).hexdigest(),
            "price_sha256": price_hashes,
        },
        "full_period_cost_stress": full_period_cost_stress,
        "calendar_windows": calendar,
        "rolling_windows": rolling,
        "summary": {
            "positive_calendar_windows": sum(row["strategy"]["total_return"] > 0 for row in calendar),
            "positive_rolling_windows": sum(row["strategy"]["total_return"] > 0 for row in rolling),
            "rolling_windows_beating_benchmark": sum(row["strategy"]["total_return"] > row["benchmark"]["total_return"] for row in rolling),
            "worst_rolling_loss_from_initial_cny": max(row["maximum_loss_from_initial_cny"] for row in rolling),
        },
        "checks": checks,
        "result": "PASS" if all(checks.values()) else "FAIL",
        "interpretation_limit": "All windows reuse data available during or after strategy discovery. Passing supports robustness to slicing and costs, not independent future profitability.",
        "capital_authorized": False,
        "orders_authorized": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"summary": output["summary"], "checks": checks, "result": output["result"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
