"""Run explicit adverse-fill stress on the exact 3000 CNY pilot scale."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from aoae.etf_momentum import load_prices, load_spec, metrics
from aoae.paper_account import load_paper_spec
from aoae.small_account import simulate_small_account


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite: {args.output}")
    raw = json.loads(args.spec.read_text(encoding="utf-8"))
    if any(raw.get(key) is not False for key in ("orders_authorized", "capital_authorized", "broker_connection_authorized")):
        raise ValueError("execution stress cannot authorize accounts, orders, or capital")
    strategy_path = Path(raw["frozen_strategy_spec"])
    pilot_path = Path(raw["pilot_account_spec"])
    strategy = load_spec(strategy_path)
    pilot = load_paper_spec(pilot_path)
    opens, closes, hashes = load_prices(Path(raw["data_dir"]), strategy.symbols)
    start, end = raw["period"]
    initial = float(pilot["initial_cash_cny"])
    rows = []
    for scenario in raw["scenarios"]:
        equity, trades, diagnostics = simulate_small_account(
            opens, closes, strategy, start, end, initial,
            float(pilot["execution"]["maximum_risk_asset_market_value_fraction"]),
            int(pilot["execution"]["buy_lot_size_shares"]),
            float(scenario["commission_rate"]), float(scenario["minimum_commission_cny"]),
            int(pilot["execution"]["volatility_lookback_days"]),
            float(pilot["execution"]["target_annualized_volatility"]),
            float(scenario["slippage_bps"]),
        )
        rows.append({
            "scenario": scenario,
            "strategy": metrics(equity, initial, start),
            "maximum_loss_from_initial_cny": round(max(0.0, initial - float(equity.min())), 2),
            "orders": sum(len(item["legs"]) for item in trades),
            "total_commission_and_slippage_cny": round(sum(float(item["cost_cny"]) for item in trades), 2),
            "cash_never_negative": diagnostics["cash_never_negative"],
        })
    limit = float(raw["decision_rule"]["all_scenarios_maximum_loss_cny_not_above"])
    checks = {
        "all_scenarios_total_return_positive": all(row["strategy"]["total_return"] > 0 for row in rows),
        "all_scenarios_maximum_loss_within_limit": all(row["maximum_loss_from_initial_cny"] <= limit for row in rows),
        "all_scenarios_cash_never_negative": all(row["cash_never_negative"] for row in rows),
    }
    record = {
        "schema_version": 1,
        "hypothesis_id": raw["hypothesis_id"],
        "record_type": "explicit_execution_cost_stress",
        "inputs": {
            "spec_sha256": sha256(args.spec.read_bytes()).hexdigest(),
            "strategy_spec_sha256": sha256(strategy_path.read_bytes()).hexdigest(),
            "pilot_spec_sha256": sha256(pilot_path.read_bytes()).hexdigest(),
            "price_sha256": hashes,
        },
        "scenarios": rows,
        "checks": checks,
        "result": "PASS" if all(checks.values()) else "FAIL",
        "interpretation_limit": "Historical adverse-fill stress is not live fill evidence and cannot replace forward observation.",
        "orders_authorized": False,
        "capital_authorized": False,
        "broker_connection_authorized": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"scenarios": rows, "checks": checks, "result": record["result"]}, ensure_ascii=False, indent=2))
    return 0 if record["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
