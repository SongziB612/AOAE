from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from aoae.etf_momentum import load_prices, load_spec, metrics
from aoae.etf_risk_overlay import simulate_overlay


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite result: {args.output}")
    raw = json.loads(args.spec.read_text(encoding="utf-8"))
    if any(raw.get(key) is not False for key in ("orders_authorized", "capital_authorized", "replacement_authorized")):
        raise ValueError("risk overlay must prohibit orders, capital, and replacement")
    root = args.spec.resolve().parents[3]
    base_spec_path = root / raw["base_signal"]["spec_path"]
    base_result = json.loads((root / raw["base_signal"]["result_path"]).read_text(encoding="utf-8"))
    base_spec = load_spec(base_spec_path)
    open_price, close, hashes = load_prices(args.data_dir, base_spec.symbols)
    if hashes != base_result["inputs"]["price_sha256"]:
        raise ValueError("inputs differ from frozen champion")
    overlay = raw["risk_overlay"]
    equity, trades = simulate_overlay(
        open_price,
        close,
        base_spec,
        int(overlay["daily_return_lookback"]),
        float(overlay["target_annualized_volatility"]),
    )
    start, end = raw["diagnostic_period"]
    mask = (equity.index >= start) & (equity.index <= end)
    prior = equity.index[equity.index < start][-1]
    result_metrics = metrics(equity.loc[mask], float(equity.at[prior]), start)
    champion = base_result["holdout"]["strategy"]
    result_calmar = result_metrics["cagr"] / abs(result_metrics["max_drawdown"])
    champion_calmar = champion["cagr"] / abs(champion["max_drawdown"])
    checks = {
        "total_return_positive": result_metrics["total_return"] > 0,
        "cagr_at_least_80_percent_of_champion": result_metrics["cagr"] >= 0.8 * champion["cagr"],
        "max_drawdown_at_least_10_percent_less_severe_than_champion": result_metrics["max_drawdown"] >= 0.9 * champion["max_drawdown"],
        "calmar_ratio_above_champion": result_calmar > champion_calmar,
        "sharpe_above_champion": result_metrics["sharpe_zero_rate"] > champion["sharpe_zero_rate"],
    }
    period_trades = [trade for trade in trades if start <= trade["execution_date"] <= end]
    status = "PASS" if all(checks.values()) else "FAIL"
    output = {
        "schema_version": 1,
        "hypothesis_id": raw["hypothesis_id"],
        "record_type": "post_holdout_historical_risk_diagnostic",
        "inputs": {"spec_sha256": sha256(args.spec.read_bytes()).hexdigest(), "price_sha256": hashes},
        "diagnostic": {
            "risk_overlay": result_metrics,
            "champion": champion,
            "risk_overlay_calmar": round(result_calmar, 8),
            "champion_calmar": round(champion_calmar, 8),
            "checks": checks,
        },
        "execution_summary": {
            "rebalances": len(period_trades),
            "average_risk_exposure": round(sum(t["risk_diagnostics"]["risk_exposure"] for t in period_trades) / len(period_trades), 8),
            "cost_cny": round(sum(t["cost_cny"] for t in period_trades), 2),
        },
        "diagnostic_rebalances": period_trades,
        "result": {
            "status": status,
            "decision": "add_as_separate_prospective_shadow_arm" if status == "PASS" else "reject_without_diagnostic_tuning",
            "champion_replaced": False,
        },
        "orders_authorized": False,
        "capital_authorized": False,
        "replacement_authorized": False,
    }
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, **output["diagnostic"], "execution_summary": output["execution_summary"]}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
