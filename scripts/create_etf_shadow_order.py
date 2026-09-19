from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

import pandas as pd

from aoae.etf_momentum import load_prices, load_spec, score_at, target_weights


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--launch-spec", type=Path, required=True)
    parser.add_argument("--champion-spec", type=Path, required=True)
    parser.add_argument("--frozen-data-dir", type=Path, required=True)
    parser.add_argument("--execution-data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite shadow order: {args.output}")

    launch = json.loads(args.launch_spec.read_text(encoding="utf-8"))
    champion = load_spec(args.champion_spec)
    open_price, close, frozen_hashes = load_prices(args.frozen_data_dir, champion.symbols)
    signal_date = pd.Timestamp(launch["signal_date"])
    execution_date = pd.Timestamp(launch["paper_execution_date"])
    i = close.index.get_loc(signal_date)
    scores = score_at(close, i, champion)
    weights = target_weights(scores, champion)

    execution_prices, observed_closes, source_hashes = {}, {}, {}
    for symbol in champion.symbols:
        path = args.execution_data_dir / f"{symbol}.csv"
        source_hashes[symbol] = sha256(path.read_bytes()).hexdigest()
        frame = pd.read_csv(path, parse_dates=["date"]).set_index("date")
        if signal_date not in frame.index or execution_date not in frame.index:
            raise ValueError(f"missing signal or execution price: {symbol}")
        if abs(float(frame.at[signal_date, "close"]) - float(close.at[signal_date, symbol])) > 1e-9:
            raise ValueError(f"Sina and frozen signal-date closes differ: {symbol}")
        execution_prices[symbol] = float(frame.at[execution_date, "open"])
        observed_closes[symbol] = {
            date.date().isoformat(): float(frame.at[date, "close"])
            for date in frame.index
            if execution_date <= date <= pd.Timestamp(launch["data"]["end_date"])
        }

    capital = float(launch["initial_paper_capital_cny"])
    cost_rate = float(launch["one_way_cost_bps"]) / 10_000
    cost = capital * cost_rate
    investable = capital - cost
    quantities = {symbol: investable * weights[symbol] / execution_prices[symbol] for symbol in champion.symbols}
    equity = {}
    for date in sorted(next(iter(observed_closes.values())).keys()):
        equity[date] = sum(quantities[symbol] * observed_closes[symbol][date] for symbol in champion.symbols)
    last_value = equity[sorted(equity)[-1]]

    result = {
        "schema_version": 1,
        "experiment_id": launch["experiment_id"],
        "record_type": "paper_shadow_launch_order",
        "classification": launch["launch_classification"],
        "signal_date": launch["signal_date"],
        "paper_execution_date": launch["paper_execution_date"],
        "model": "frozen_monthly_dual_momentum_champion",
        "scores": {symbol: round(value, 8) for symbol, value in scores.items()},
        "target_weights": {symbol: weight for symbol, weight in weights.items() if weight},
        "paper_order": {
            "initial_capital_cny": capital,
            "one_way_cost_bps": float(launch["one_way_cost_bps"]),
            "estimated_cost_cny": round(cost, 2),
            "fractional_accounting": True,
            "legs": [
                {
                    "symbol": symbol,
                    "side": "BUY",
                    "target_weight": weights[symbol],
                    "paper_fill_open": execution_prices[symbol],
                    "paper_quantity": round(quantities[symbol], 6),
                    "paper_notional_cny": round(investable * weights[symbol], 2),
                }
                for symbol in champion.symbols
                if weights[symbol]
            ],
        },
        "observed_paper_equity": {date: round(value, 2) for date, value in equity.items()},
        "observed_return_through_data_end": round(last_value / capital - 1, 8),
        "inputs": {"frozen_price_sha256": frozen_hashes, "execution_snapshot_sha256": source_hashes},
        "prospective_score_eligible": False,
        "reason_not_prospective": "order record was created on 2026-09-03 after the 2026-09-01 paper execution date",
        "orders_authorized": False,
        "capital_authorized": False,
        "broker_connection_authorized": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
