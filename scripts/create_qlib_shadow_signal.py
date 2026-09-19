from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from aoae.etf_momentum import load_prices
from aoae.qlib_challenger import build_monthly_samples, prediction_schedule


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--launch-spec", type=Path, required=True)
    parser.add_argument("--qlib-spec", type=Path, required=True)
    parser.add_argument("--frozen-data-dir", type=Path, required=True)
    parser.add_argument("--execution-data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite observer signal: {args.output}")
    launch = json.loads(args.launch_spec.read_text(encoding="utf-8"))
    spec = json.loads(args.qlib_spec.read_text(encoding="utf-8"))
    risk_assets = tuple(spec["inputs"]["risk_assets"])
    defensive = spec["inputs"]["defensive_asset"]
    symbols = risk_assets + (defensive,)
    open_price, close, _ = load_prices(args.frozen_data_dir, symbols)

    volumes, extra_opens, extra_closes = {}, {}, {}
    for symbol in symbols:
        frozen = pd.read_csv(args.frozen_data_dir / f"{symbol}.csv", parse_dates=["date"]).set_index("date")
        recent = pd.read_csv(args.execution_data_dir / f"{symbol}.csv", parse_dates=["date"]).set_index("date")
        extra = recent.loc[recent.index > close.index[-1]]
        extra_opens[symbol] = extra["open"]
        extra_closes[symbol] = extra["close"]
        volumes[symbol] = pd.concat([frozen["volume"], extra["volume"]])
    open_price = pd.concat([open_price, pd.concat(extra_opens, axis=1, join="inner")]).sort_index()
    close = pd.concat([close, pd.concat(extra_closes, axis=1, join="inner")]).sort_index()
    volume = pd.concat(volumes, axis=1).loc[close.index]
    samples = build_monthly_samples(open_price, close, volume, risk_assets)

    dates = samples.frame.index.get_level_values("datetime")
    realized = samples.label_realized_dates
    train = (dates >= "2016-01-01") & (dates <= "2020-12-31") & (realized <= pd.Timestamp("2020-12-31")).to_numpy()
    valid = (dates >= "2021-01-01") & (dates <= "2021-12-31") & (realized <= pd.Timestamp("2021-12-31")).to_numpy()
    observer = dates == pd.Timestamp(launch["signal_date"])
    frame = samples.frame.loc[train | valid | observer]

    from qlib.contrib.model import gbdt
    from qlib.data.dataset import DatasetH
    from qlib.data.dataset.handler import DataHandlerLP

    gbdt.R.log_metrics = lambda **kwargs: None
    segments = {
        "train": (pd.Timestamp("2016-01-29"), pd.Timestamp("2020-10-30")),
        "valid": (pd.Timestamp("2021-01-29"), pd.Timestamp("2021-10-29")),
        "test": (pd.Timestamp(launch["signal_date"]), pd.Timestamp(launch["signal_date"])),
    }
    dataset = DatasetH(DataHandlerLP.from_df(frame), segments=segments)
    model_raw = spec["model"]
    ignored = {"framework", "qlib_version", "lightgbm_version", "loss", "early_stopping_rounds", "num_boost_round"}
    model = gbdt.LGBModel(
        loss=model_raw["loss"],
        early_stopping_rounds=model_raw["early_stopping_rounds"],
        num_boost_round=model_raw["num_boost_round"],
        **{key: value for key, value in model_raw.items() if key not in ignored},
    )
    model.fit(dataset, verbose_eval=0)
    predictions = model.predict(dataset, segment="test")
    schedule = prediction_schedule(
        predictions,
        samples.execution_dates.loc[predictions.index],
        symbols,
        risk_assets,
        defensive,
        int(spec["portfolio"]["top_n"]),
    )
    execution_date = pd.Timestamp(launch["paper_execution_date"])
    weights, scores, signal_date = schedule[execution_date]
    output = {
        "schema_version": 1,
        "experiment_id": launch["experiment_id"],
        "record_type": "rejected_qlib_observer_signal",
        "signal_date": signal_date,
        "paper_execution_date": launch["paper_execution_date"],
        "best_iteration": int(model.model.best_iteration),
        "predictions": {symbol: round(value, 8) for symbol, value in scores.items()},
        "observer_weights": {symbol: weight for symbol, weight in weights.items() if weight},
        "may_replace_champion": False,
        "reason": "Qlib challenger failed the preregistered maximum-drawdown gate",
        "orders_authorized": False,
        "capital_authorized": False,
    }
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
