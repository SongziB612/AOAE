from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path

from aoae.etf_momentum import load_prices, load_spec, metrics, simulate, simulate_benchmark


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite audit: {args.output}")
    spec = load_spec(args.spec)
    expected = json.loads(args.result.read_text(encoding="utf-8"))
    open_price, close, hashes = load_prices(args.data_dir, spec.symbols)
    mask = (close.index >= spec.holdout_start) & (close.index <= spec.holdout_end)
    prior = close.index[close.index < spec.holdout_start][-1]
    stress = {}
    for bps in (0, 15, 30, 50):
        stressed = replace(spec, cost_rate=bps / 10_000)
        equity, _, _, _ = simulate(open_price, close, stressed)
        stress[str(bps)] = metrics(equity.loc[mask], float(equity.at[prior]), spec.holdout_start)
    benchmark = simulate_benchmark(open_price, close, spec)
    benchmark_metrics = metrics(benchmark.loc[mask], float(benchmark.at[prior]), spec.holdout_start)
    checks = {
        "raw_hashes_match_result": hashes == expected["inputs"]["price_sha256"],
        "base_metrics_reproduce_exactly": stress["15"] == expected["holdout"]["strategy"],
        "benchmark_metrics_reproduce_exactly": benchmark_metrics == expected["holdout"]["benchmark"],
        "positive_cagr_at_50bps": stress["50"]["cagr"] > 0,
        "beats_benchmark_cagr_at_50bps": stress["50"]["cagr"] > benchmark_metrics["cagr"],
    }
    output = {
        "schema_version": 1,
        "audit_type": "post_holdout_cost_stress_and_reproduction",
        "not_a_new_strategy_trial": True,
        "cost_stress_one_way_bps": stress,
        "benchmark": benchmark_metrics,
        "checks": checks,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "orders_authorized": False,
        "capital_authorized": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
