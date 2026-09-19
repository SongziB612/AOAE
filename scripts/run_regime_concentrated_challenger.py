"""Run the single preregistered high-conviction ETF challenger."""

from __future__ import annotations

import argparse
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

from aoae.etf_momentum import load_prices, load_spec, metrics
from aoae.small_account import executable_benchmark, simulate_small_account


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite: {args.output}")
    raw = json.loads(args.spec.read_text(encoding="utf-8"))
    if any(raw.get(key) is not False for key in ("orders_authorized", "capital_authorized", "broker_connection_authorized")):
        raise ValueError("research cannot authorize accounts, orders, or capital")

    base_path = Path(raw["frozen_base_spec"])
    base = load_spec(base_path)
    method = raw["method"]
    concentrated = replace(base, top_n=1, initial_capital=float(method["initial_and_maximum_capital_cny"]))
    opens, closes, hashes = load_prices(Path(raw["data_dir"]), concentrated.symbols)
    start, end = raw["period"]
    initial = float(method["initial_and_maximum_capital_cny"])
    equity, trades, diagnostics = simulate_small_account(
        opens,
        closes,
        concentrated,
        start,
        end,
        initial,
        float(method["maximum_risk_exposure"]),
        int(method["buy_lot_size_shares"]),
        float(method["one_way_cost_rate"]),
        float(method["minimum_cost_per_order_cny"]),
        int(method["volatility_lookback_days"]),
        float(method["target_annualized_volatility"]),
    )
    benchmark = executable_benchmark(
        opens,
        closes,
        concentrated.benchmark,
        start,
        end,
        initial,
        int(method["buy_lot_size_shares"]),
        float(method["one_way_cost_rate"]),
        float(method["minimum_cost_per_order_cny"]),
    )
    strategy_metrics = metrics(equity, initial, start)
    benchmark_metrics = metrics(benchmark, initial, start)
    maximum_loss = max(0.0, initial - float(equity.min()))
    calendar_years = []
    for year in range(2022, 2027):
        window = equity[equity.index.year == year]
        if len(window):
            baseline = initial if year == 2022 else float(equity[equity.index < window.index[0]].iloc[-1])
            calendar_years.append({"year": year, **metrics(window, baseline, f"{year}-01-01")})
    rule = raw["decision_rule"]
    checks = {
        "net_total_return_positive": strategy_metrics["total_return"] > 0,
        "beats_executable_510300_buy_and_hold": strategy_metrics["total_return"] > benchmark_metrics["total_return"],
        "maximum_historical_loss_within_sleeve": maximum_loss <= float(rule["maximum_historical_loss_cny_not_above"]),
        "cash_never_negative": diagnostics["cash_never_negative"] is True,
        "minimum_positive_calendar_years": sum(row["total_return"] > 0 for row in calendar_years) >= int(rule["minimum_positive_calendar_years"]),
    }
    passed = all(checks.values())
    record = {
        "schema_version": 1,
        "hypothesis_id": raw["hypothesis_id"],
        "record_type": "post_discovery_high_conviction_diagnostic",
        "inputs": {
            "spec_sha256": sha256(args.spec.read_bytes()).hexdigest(),
            "base_spec_sha256": sha256(base_path.read_bytes()).hexdigest(),
            "price_sha256": hashes,
        },
        "strategy": strategy_metrics,
        "benchmark": benchmark_metrics,
        "maximum_loss_from_initial_cny": round(maximum_loss, 2),
        "calendar_years": calendar_years,
        "orders": sum(len(item["legs"]) for item in trades),
        "cost_cny": round(sum(float(item["cost_cny"]) for item in trades), 2),
        "diagnostics": diagnostics,
        "checks": checks,
        "result": "HISTORICAL_DIAGNOSTIC_PASS_FORWARD_REQUIRED" if passed else "REJECT_EXACT_RULE",
        "interpretation_limit": "Post-discovery history can reject this rule, but cannot establish future profitability.",
        "orders_authorized": False,
        "capital_authorized": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: record[key] for key in ("strategy", "benchmark", "maximum_loss_from_initial_cny", "calendar_years", "orders", "cost_cny", "checks", "result")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
