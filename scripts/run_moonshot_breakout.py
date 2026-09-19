from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

import pandas as pd

from aoae.etf_momentum import metrics
from aoae.moonshot_breakout import executable_buy_hold, simulate_breakout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite result: {args.output}")
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    symbols = tuple(spec["data"]["universe"])
    open_columns, close_columns, hashes = {}, {}, {}
    for symbol in symbols:
        path = args.data_dir / f"{symbol}.csv"
        payload = path.read_bytes()
        digest = sha256(payload).hexdigest()
        if digest != manifest["files"][symbol]["sha256"]:
            raise ValueError(f"data hash mismatch: {symbol}")
        frame = pd.read_csv(path, parse_dates=["date"]).sort_values("date").set_index("date")
        open_columns[symbol], close_columns[symbol], hashes[symbol] = frame["open"], frame["close"], digest
    opens = pd.concat(open_columns, axis=1, join="inner").sort_index()
    closes = pd.concat(close_columns, axis=1, join="inner").sort_index()
    method = spec["method"]
    start, end = spec["qualification_period"]
    equity, events, closed = simulate_breakout(
        opens, closes, start, end,
        float(method["initial_and_maximum_capital_cny"]),
        55, 20, 63, int(method["buy_lot_size_shares"]),
        float(method["commission_rate_one_way"]),
        float(method["minimum_commission_per_order_cny"]),
        float(method["slippage_bps_one_way"]),
    )
    benchmark = executable_buy_hold(
        opens, closes, "159915", start, end,
        float(method["initial_and_maximum_capital_cny"]), int(method["buy_lot_size_shares"]),
        float(method["commission_rate_one_way"]), float(method["minimum_commission_per_order_cny"]),
        float(method["slippage_bps_one_way"]),
    )
    initial = float(method["initial_and_maximum_capital_cny"])
    strategy_metrics = metrics(equity, initial, start)
    benchmark_metrics = metrics(benchmark, initial, start)
    gains = sum(max(float(trade["trade_net_pnl_cny"]), 0) for trade in closed)
    losses = -sum(min(float(trade["trade_net_pnl_cny"]), 0) for trade in closed)
    profit_factor = gains / losses if losses else (float("inf") if gains else 0.0)
    maximum_loss = max(0.0, initial - float(equity.min()))
    checks = {
        "net_total_return_positive": strategy_metrics["total_return"] > 0,
        "minimum_closed_trades": len(closed) >= int(spec["decision_rule"]["minimum_closed_trades"]),
        "profit_factor_above_one": profit_factor > 1,
        "maximum_loss_not_above_funded_sleeve": maximum_loss <= initial,
        "beats_executable_159915_buy_and_hold": strategy_metrics["total_return"] > benchmark_metrics["total_return"],
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    output = {
        "schema_version": 1,
        "hypothesis_id": spec["hypothesis_id"],
        "record_type": "post_registration_moonshot_qualification",
        "inputs": {"spec_sha256": sha256(args.spec.read_bytes()).hexdigest(), "manifest_sha256": sha256(args.manifest.read_bytes()).hexdigest(), "price_sha256": hashes},
        "strategy": strategy_metrics,
        "executable_159915_buy_and_hold": benchmark_metrics,
        "closed_trades": len(closed),
        "profit_factor": round(profit_factor, 6),
        "maximum_loss_from_initial_cny": round(maximum_loss, 2),
        "events": events,
        "checks": checks,
        "result": {"status": status, "decision": spec["next_step_if_pass"] if status == "PASS" else spec["next_step_if_fail"]},
        "orders_authorized": False,
        "capital_authorized": False,
    }
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: output[key] for key in ("strategy", "executable_159915_buy_and_hold", "closed_trades", "profit_factor", "maximum_loss_from_initial_cny", "checks", "result")}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
