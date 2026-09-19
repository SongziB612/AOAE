"""Leakage-aware expanding-window evaluation for small tabular time series."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import version
import math
from typing import Sequence

import numpy as np
import scipy
from sklearn.linear_model import Ridge
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


@dataclass(frozen=True)
class WalkForwardConfig:
    n_splits: int
    test_size: int
    gap: int
    target_horizon_observations: int
    minimum_train_size: int
    ridge_alpha: float

    def validate(self) -> None:
        if self.n_splits < 2:
            raise ValueError("n_splits must be at least two")
        if self.test_size < 1 or self.target_horizon_observations < 1:
            raise ValueError("test_size and target_horizon_observations must be positive")
        if self.gap < self.target_horizon_observations:
            raise ValueError("gap must cover the full target horizon")
        if self.minimum_train_size < 30:
            raise ValueError("minimum_train_size must be at least 30")
        if not math.isfinite(self.ridge_alpha) or self.ridge_alpha <= 0:
            raise ValueError("ridge_alpha must be finite and positive")


def _rounded(value: float) -> float:
    return round(float(value), 12)


def _metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float | None]:
    errors = predicted - actual
    actual_std = float(np.std(actual))
    predicted_std = float(np.std(predicted))
    correlation = None
    if actual_std > 0 and predicted_std > 0:
        correlation = _rounded(np.corrcoef(actual, predicted)[0, 1])
    return {
        "mae": _rounded(np.mean(np.abs(errors))),
        "rmse": _rounded(np.sqrt(np.mean(errors ** 2))),
        "correlation": correlation,
        "direction_accuracy": _rounded(np.mean(np.sign(actual) == np.sign(predicted))),
    }


def evaluate_walk_forward(
    features: Sequence[Sequence[float]],
    targets: Sequence[float],
    config: WalkForwardConfig,
) -> dict[str, object]:
    """Fit Ridge per expanding fold and compare only out-of-sample predictions."""

    config.validate()
    x = np.asarray(features, dtype=float)
    y = np.asarray(targets, dtype=float)
    if x.ndim != 2 or y.ndim != 1 or len(x) != len(y):
        raise ValueError("features must be 2D and align one-to-one with 1D targets")
    if len(x) == 0 or x.shape[1] == 0 or not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("features and targets must be non-empty and finite")

    splitter = TimeSeriesSplit(
        n_splits=config.n_splits,
        test_size=config.test_size,
        gap=config.gap,
    )
    folds: list[dict[str, object]] = []
    prediction_rows: list[dict[str, float | int]] = []
    all_actual: list[float] = []
    all_model: list[float] = []
    all_baseline: list[float] = []

    try:
        splits = list(splitter.split(x))
    except ValueError as exc:
        raise ValueError(f"walk-forward split is infeasible: {exc}") from exc
    if len(splits[0][0]) < config.minimum_train_size:
        raise ValueError("first training window is smaller than minimum_train_size")

    for fold_number, (train_indices, test_indices) in enumerate(splits, start=1):
        if train_indices[-1] + config.gap >= test_indices[0]:
            raise AssertionError("training/test gap invariant failed")
        model = Pipeline([
            ("scale", StandardScaler()),
            ("ridge", Ridge(alpha=config.ridge_alpha, solver="svd")),
        ])
        model.fit(x[train_indices], y[train_indices])
        model_predictions = model.predict(x[test_indices])
        baseline_predictions = np.full(len(test_indices), np.mean(y[train_indices]))
        actual = y[test_indices]

        folds.append({
            "fold": fold_number,
            "train_start": int(train_indices[0]),
            "train_end": int(train_indices[-1]),
            "train_size": len(train_indices),
            "gap_size": int(test_indices[0] - train_indices[-1] - 1),
            "test_start": int(test_indices[0]),
            "test_end": int(test_indices[-1]),
            "test_size": len(test_indices),
            "model_metrics": _metrics(actual, model_predictions),
            "train_mean_baseline_metrics": _metrics(actual, baseline_predictions),
        })
        for index, observed, predicted, baseline in zip(
            test_indices, actual, model_predictions, baseline_predictions, strict=True
        ):
            prediction_rows.append({
                "index": int(index),
                "actual": _rounded(observed),
                "model_prediction": _rounded(predicted),
                "train_mean_baseline_prediction": _rounded(baseline),
            })
        all_actual.extend(actual.tolist())
        all_model.extend(model_predictions.tolist())
        all_baseline.extend(baseline_predictions.tolist())

    actual_array = np.asarray(all_actual)
    model_array = np.asarray(all_model)
    baseline_array = np.asarray(all_baseline)
    model_metrics = _metrics(actual_array, model_array)
    baseline_metrics = _metrics(actual_array, baseline_array)
    beats_baseline = (
        model_metrics["mae"] < baseline_metrics["mae"]
        and model_metrics["rmse"] < baseline_metrics["rmse"]
    )
    return {
        "schema_version": 1,
        "record_type": "walk_forward_model_evaluation",
        "implementation": {
            "library": "scikit-learn",
            "version": version("scikit-learn"),
            "numpy_version": np.__version__,
            "scipy_version": scipy.__version__,
            "splitter": "TimeSeriesSplit",
            "estimator": "StandardScaler_then_Ridge_svd",
        },
        "configuration": {
            "n_splits": config.n_splits,
            "test_size": config.test_size,
            "gap": config.gap,
            "target_horizon_observations": config.target_horizon_observations,
            "minimum_train_size": config.minimum_train_size,
            "ridge_alpha": config.ridge_alpha,
        },
        "sample": {
            "rows": len(x),
            "features": x.shape[1],
            "out_of_sample_predictions": len(all_actual),
        },
        "folds": folds,
        "aggregate": {
            "model_metrics": model_metrics,
            "train_mean_baseline_metrics": baseline_metrics,
            "model_beats_baseline_on_mae_and_rmse": beats_baseline,
        },
        "predictions": prediction_rows,
        "interpretation": "Evaluation capability only; a favorable score is not evidence of alpha or authorization to trade.",
        "strategy_mining_authorized": False,
        "capital_authorized": False,
    }
