"""Post-result scale diagnostic: isolate minimum-commission drag."""

from __future__ import annotations

import argparse
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

from aoae.etf_momentum import load_prices, load_spec, metrics
from aoae.small_account import simulate_small_account


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--failed-result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite: {args.output}")
    raw = json.loads(args.spec.read_text(encoding="utf-8"))
    method = raw["method"]
    base = load_spec(Path(raw["frozen_base_spec"]))
    concentrated = replace(base, top_n=1)
    opens, closes, hashes = load_prices(Path(raw["data_dir"]), concentrated.symbols)
    rows = []
    for capital in (1000.0, 3000.0, 10000.0):
        sized = replace(concentrated, initial_capital=capital)
        equity, trades, diagnostics = simulate_small_account(
            opens, closes, sized, raw["period"][0], raw["period"][1], capital,
            float(method["maximum_risk_exposure"]), int(method["buy_lot_size_shares"]),
            float(method["one_way_cost_rate"]), float(method["minimum_cost_per_order_cny"]),
            int(method["volatility_lookback_days"]), float(method["target_annualized_volatility"]),
        )
        costs = sum(float(item["cost_cny"]) for item in trades)
        rows.append({
            "capital_cny": capital,
            "strategy": metrics(equity, capital, raw["period"][0]),
            "maximum_loss_from_initial_cny": round(max(0.0, capital - float(equity.min())), 2),
            "orders": sum(len(item["legs"]) for item in trades),
            "cost_cny": round(costs, 2),
            "cost_as_initial_capital_fraction": round(costs / capital, 6),
            "cash_never_negative": diagnostics["cash_never_negative"],
        })
    record = {
        "schema_version": 1,
        "record_type": "post_result_transaction_cost_scale_diagnostic",
        "warning": "Created after observing the 1000 CNY failure; descriptive only and not a new clean trial.",
        "inputs": {
            "spec_sha256": sha256(args.spec.read_bytes()).hexdigest(),
            "failed_result_sha256": sha256(args.failed_result.read_bytes()).hexdigest(),
            "price_sha256": hashes,
        },
        "scales": rows,
        "orders_authorized": False,
        "capital_authorized": False,
    }
    args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
