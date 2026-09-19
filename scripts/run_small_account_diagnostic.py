from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from aoae.etf_momentum import load_prices, load_spec, metrics
from aoae.small_account import executable_benchmark, simulate_small_account


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite diagnostic: {args.output}")
    raw = json.loads(args.spec.read_text(encoding="utf-8"))
    frozen = raw["frozen_inputs"]
    root = args.repo_root.resolve()
    for path_key, hash_key in (("overlay_spec_path", "overlay_spec_sha256"), ("overlay_result_path", "overlay_result_sha256"), ("paper_account_spec_path", "paper_account_spec_sha256")):
        path = root / frozen[path_key]
        if sha256(path.read_bytes()).hexdigest() != frozen[hash_key]:
            raise ValueError(f"frozen input changed: {path_key}")
    if "champion_result_path" in frozen:
        champion_path = root / frozen["champion_result_path"]
        if sha256(champion_path.read_bytes()).hexdigest() != frozen["champion_result_sha256"]:
            raise ValueError("frozen input changed: champion_result_path")
    overlay_spec = json.loads((root / frozen["overlay_spec_path"]).read_text(encoding="utf-8"))
    overlay_result = json.loads((root / frozen["overlay_result_path"]).read_text(encoding="utf-8"))
    paper_spec = json.loads((root / frozen["paper_account_spec_path"]).read_text(encoding="utf-8"))
    base_spec = load_spec(root / overlay_spec["base_signal"]["spec_path"])
    open_price, close, hashes = load_prices(args.data_dir, base_spec.symbols)
    if hashes != overlay_result["inputs"]["price_sha256"]:
        raise ValueError("price inputs changed")
    execution = raw["execution"]
    start, end = raw["period"]
    equity, trades, execution_checks = simulate_small_account(
        open_price, close, base_spec, start, end,
        float(execution["initial_cash_cny"]), float(execution["risk_asset_market_value_cap_fraction"]),
        int(execution["buy_lot_size_shares"]), float(execution["one_way_cost_rate"]),
        float(execution["minimum_cost_per_nonzero_order_cny"]),
        int(execution.get("volatility_lookback_days", 63)),
        float(execution.get("target_annualized_volatility", 0.12)),
    )
    benchmark_equity = executable_benchmark(
        open_price, close, base_spec.benchmark, start, end,
        float(execution["initial_cash_cny"]), int(execution["buy_lot_size_shares"]),
        float(execution["one_way_cost_rate"]), float(execution["minimum_cost_per_nonzero_order_cny"]),
    )
    sm = metrics(equity, float(execution["initial_cash_cny"]), start)
    bm = metrics(benchmark_equity, float(execution["initial_cash_cny"]), start)
    maximum_loss = max(0.0, float(execution["initial_cash_cny"]) - float(equity.min()))
    drawdown_limit = float(paper_spec["risk_limits"]["maximum_acceptable_drawdown_fraction"])
    drawdown_check_name = f"maximum_drawdown_not_below_negative_{round(drawdown_limit * 100):g}_percent"
    loss_limit = float(paper_spec["risk_limits"]["maximum_acceptable_loss_cny"])
    loss_check_name = f"maximum_historical_loss_cny_not_above_{round(loss_limit):g}"
    checks = {
        "total_return_positive": sm["total_return"] > 0,
        "cagr_above_510300_benchmark": sm["cagr"] > bm["cagr"],
        drawdown_check_name: sm["max_drawdown"] >= -drawdown_limit,
        loss_check_name: maximum_loss <= loss_limit,
        "all_buys_are_100_share_multiples": execution_checks["all_buys_are_lot_multiples"],
        "cash_never_negative": execution_checks["cash_never_negative"],
    }
    if "champion_result_path" in frozen:
        champion = json.loads((root / frozen["champion_result_path"]).read_text(encoding="utf-8"))
        checks["cagr_above_frozen_small_account_champion"] = sm["cagr"] > champion["small_account"]["cagr"]
    status = "PASS" if all(checks.values()) else "FAIL"
    output = {
        "schema_version": 1,
        "hypothesis_id": raw["hypothesis_id"],
        "record_type": "post_holdout_small_account_feasibility_diagnostic",
        "inputs": {"spec_sha256": sha256(args.spec.read_bytes()).hexdigest(), "price_sha256": hashes},
        "small_account": sm,
        "executable_510300_benchmark": bm,
        "maximum_loss_from_initial_cny": round(maximum_loss, 2),
        "execution_checks": execution_checks,
        "execution_summary": {"rebalances": len(trades), "orders": sum(len(t["legs"]) for t in trades), "total_cost_cny": round(sum(t["cost_cny"] for t in trades), 2)},
        "checks": checks,
        "rebalances": trades,
        "result": {"status": status, "decision": raw["next_step_if_pass"] if status == "PASS" else raw["next_step_if_fail"]},
        "orders_authorized": False,
        "capital_authorized": False,
    }
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: output[k] for k in ("small_account", "executable_510300_benchmark", "maximum_loss_from_initial_cny", "execution_checks", "execution_summary", "checks", "result")}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
