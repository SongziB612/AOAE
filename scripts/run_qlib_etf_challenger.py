from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
import warnings

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from aoae.etf_momentum import load_prices, metrics
from aoae.qlib_challenger import (
    FEATURES,
    build_monthly_samples,
    mean_monthly_spearman_ic,
    prediction_schedule,
    simulate_schedule,
)


def load_inputs(spec_path: Path, data_dir: Path):
    raw = json.loads(spec_path.read_text(encoding="utf-8"))
    if any(raw.get(key) is not False for key in ("orders_authorized", "capital_authorized", "replacement_authorized")):
        raise ValueError("challenger specification must prohibit orders, capital, and replacement")
    root = spec_path.parents[3]
    champion_path = root / raw["inputs"]["champion_result_path"]
    champion = json.loads(champion_path.read_text(encoding="utf-8"))
    symbols = tuple(raw["inputs"]["risk_assets"] + [raw["inputs"]["defensive_asset"]])
    open_price, close, hashes = load_prices(data_dir, symbols)
    if hashes != champion["inputs"]["price_sha256"]:
        raise ValueError("price files do not match the frozen champion inputs")

    volumes = {}
    for symbol in symbols:
        frame = pd.read_csv(data_dir / f"{symbol}.csv", parse_dates=["date"]).sort_values("date").set_index("date")
        if "volume" not in frame or frame["volume"].isna().any() or (frame["volume"] < 0).any():
            raise ValueError(f"invalid volume: {symbol}")
        volumes[symbol] = frame["volume"]
    volume = pd.concat(volumes, axis=1, join="inner").loc[close.index]
    return raw, champion, symbols, open_price, close, volume, hashes


def eligible_rows(samples, start: str, end: str, require_realized: bool) -> pd.Series:
    dates = samples.frame.index.get_level_values("datetime")
    selected = (dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end))
    if require_realized:
        selected &= samples.label_realized_dates.notna().to_numpy()
        selected &= (samples.label_realized_dates <= pd.Timestamp(end)).to_numpy()
    return pd.Series(selected, index=samples.frame.index)


def run(spec_path: Path, data_dir: Path) -> dict:
    raw, champion, symbols, open_price, close, volume, hashes = load_inputs(spec_path, data_dir)
    risk_assets = tuple(raw["inputs"]["risk_assets"])
    defensive = raw["inputs"]["defensive_asset"]
    samples = build_monthly_samples(open_price, close, volume, risk_assets)
    dataset_spec = raw["dataset"]

    train_mask = eligible_rows(samples, *dataset_spec["training"], require_realized=True)
    valid_mask = eligible_rows(samples, *dataset_spec["validation"], require_realized=True)
    qualification_start, qualification_end = dataset_spec["qualification"]
    execution_values = samples.execution_dates
    qualification_mask = (execution_values >= pd.Timestamp(qualification_start)) & (execution_values <= pd.Timestamp(qualification_end))
    selected = train_mask | valid_mask | qualification_mask
    model_frame = samples.frame.loc[selected].copy()
    if model_frame.empty or model_frame.loc[:, "feature"].isna().any().any():
        raise ValueError("empty dataset or missing model feature")

    train_dates = model_frame.index.get_level_values("datetime")[train_mask.loc[selected].to_numpy()]
    valid_dates = model_frame.index.get_level_values("datetime")[valid_mask.loc[selected].to_numpy()]
    qualification_dates = model_frame.index.get_level_values("datetime")[qualification_mask.loc[selected].to_numpy()]
    segments = {
        "train": (train_dates.min(), train_dates.max()),
        "valid": (valid_dates.min(), valid_dates.max()),
        "test": (qualification_dates.min(), qualification_dates.max()),
    }

    from qlib.data.dataset import DatasetH
    from qlib.data.dataset.handler import DataHandlerLP
    from qlib.contrib.model import gbdt

    gbdt.R.log_metrics = lambda **kwargs: None
    dataset = DatasetH(handler=DataHandlerLP.from_df(model_frame), segments=segments)
    model_spec = raw["model"]
    constructor_keys = {"loss", "early_stopping_rounds", "num_boost_round"}
    constructor = {key: model_spec[key] for key in constructor_keys}
    aliases = {"early_stopping_rounds": "early_stopping_rounds"}
    constructor = {aliases.get(key, key): value for key, value in constructor.items()}
    ignored = {"framework", "qlib_version", "lightgbm_version"} | constructor_keys
    parameters = {key: value for key, value in model_spec.items() if key not in ignored}
    model = gbdt.LGBModel(**constructor, **parameters)
    evals_result = {}
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*The argument 'feature_name'.*")
        model.fit(dataset, verbose_eval=0, evals_result=evals_result)
        predictions = model.predict(dataset, segment="test")
    predictions.name = "prediction"

    test_execution_dates = samples.execution_dates.loc[predictions.index]
    schedule = prediction_schedule(
        predictions,
        test_execution_dates,
        symbols,
        risk_assets,
        defensive,
        int(raw["portfolio"]["top_n"]),
    )
    holdout_mask = (close.index >= qualification_start) & (close.index <= qualification_end)
    holdout_open, holdout_close = open_price.loc[holdout_mask], close.loc[holdout_mask]
    equity, trades = simulate_schedule(
        holdout_open,
        holdout_close,
        schedule,
        symbols,
        float(raw["portfolio"]["initial_capital_cny"]),
        float(raw["portfolio"]["one_way_cost_bps"]) / 10_000,
    )
    challenger_metrics = metrics(
        equity,
        float(raw["portfolio"]["initial_capital_cny"]),
        qualification_start,
    )
    champion_metrics = champion["holdout"]["strategy"]

    realized_mask = qualification_mask & samples.label_realized_dates.notna()
    realized_mask &= samples.label_realized_dates <= pd.Timestamp(qualification_end)
    realized_index = samples.frame.index[realized_mask]
    ic, ic_months = mean_monthly_spearman_ic(
        predictions.loc[predictions.index.intersection(realized_index)],
        samples.frame.loc[predictions.index.intersection(realized_index), ("label", "LABEL0")],
    )
    checks = {
        "qualification_total_return_positive": challenger_metrics["total_return"] > 0,
        "qualification_cagr_above_champion": challenger_metrics["cagr"] > champion_metrics["cagr"],
        "qualification_max_drawdown_less_severe_than_champion": challenger_metrics["max_drawdown"] > champion_metrics["max_drawdown"],
        "qualification_sharpe_above_champion": challenger_metrics["sharpe_zero_rate"] > champion_metrics["sharpe_zero_rate"],
        "mean_monthly_spearman_ic_above_zero": bool(np.isfinite(ic) and ic > 0),
    }
    importance = {
        name: round(float(value), 8)
        for name, value in zip(model.model.feature_name(), model.model.feature_importance(importance_type="gain"))
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    return {
        "schema_version": 1,
        "hypothesis_id": raw["hypothesis_id"],
        "record_type": "post_champion_qualification_test",
        "inputs": {
            "spec_sha256": sha256(spec_path.read_bytes()).hexdigest(),
            "price_sha256": hashes,
            "common_first_date": close.index[0].date().isoformat(),
            "common_last_date": close.index[-1].date().isoformat(),
        },
        "environment": {
            "qlib": raw["model"]["qlib_version"],
            "lightgbm": raw["model"]["lightgbm_version"],
            "telemetry_disabled": "R.log_metrics only",
            "execution_attempts": 2,
            "first_attempt_incident": "model fit completed but result serialization failed before qualification output because evals_result is nested; no parameter or rule changed",
        },
        "dataset": {
            "train_rows": int(train_mask.sum()),
            "validation_rows": int(valid_mask.sum()),
            "qualification_prediction_rows": len(predictions),
            "qualification_rebalances": len(trades),
            "qualification_ic_months": ic_months,
            "segments_by_signal_date": {key: [str(value[0].date()), str(value[1].date())] for key, value in segments.items()},
        },
        "model": {
            "best_iteration": int(model.model.best_iteration),
            "feature_order": list(FEATURES),
            "feature_importance_gain": importance,
            "validation_history": {
                dataset_name: {
                    metric_name: [round(float(x), 10) for x in values]
                    for metric_name, values in metrics_at_dataset.items()
                }
                for dataset_name, metrics_at_dataset in evals_result.items()
            },
        },
        "qualification": {
            "challenger": challenger_metrics,
            "champion": champion_metrics,
            "mean_monthly_spearman_ic": round(ic, 8) if np.isfinite(ic) else None,
            "checks": checks,
        },
        "qualification_rebalances": trades,
        "result": {
            "status": status,
            "decision": "advance_to_three_month_prospective_shadow_test" if status == "PASS" else "reject_without_qualification_tuning",
            "champion_replaced": False,
        },
        "orders_authorized": False,
        "capital_authorized": False,
        "replacement_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite result: {args.output}")
    result = run(args.spec.resolve(), args.data_dir.resolve())
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["result"]["status"], **result["qualification"]}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
