"""Auditable evaluation for market-anchored binary probability forecasts."""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np


def _probabilities(values: Sequence[float], name: str) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.ndim != 1 or len(array) == 0:
        raise ValueError(f"{name} must be a non-empty one-dimensional sequence")
    if not np.isfinite(array).all() or np.any(array < 0) or np.any(array > 1):
        raise ValueError(f"{name} must contain finite probabilities in [0, 1]")
    return array


def market_anchored_probabilities(
    market_probabilities: Sequence[float],
    log_odds_adjustments: Sequence[float],
    maximum_absolute_adjustment: float,
) -> list[float]:
    """Apply capped model adjustments to market log odds."""

    market = _probabilities(market_probabilities, "market_probabilities")
    adjustments = np.asarray(log_odds_adjustments, dtype=float)
    if adjustments.ndim != 1 or len(adjustments) != len(market) or not np.isfinite(adjustments).all():
        raise ValueError("log_odds_adjustments must be finite and align with market probabilities")
    if (
        isinstance(maximum_absolute_adjustment, bool)
        or not math.isfinite(maximum_absolute_adjustment)
        or not 0 < maximum_absolute_adjustment <= 10
    ):
        raise ValueError("maximum_absolute_adjustment must be finite and in (0, 10]")
    epsilon = 1e-12
    clipped_market = np.clip(market, epsilon, 1 - epsilon)
    market_logits = np.log(clipped_market / (1 - clipped_market))
    capped_adjustments = np.clip(
        adjustments, -maximum_absolute_adjustment, maximum_absolute_adjustment
    )
    combined = market_logits + capped_adjustments
    probabilities = 1 / (1 + np.exp(-combined))
    return [round(float(value), 12) for value in probabilities]


def _score(outcomes: np.ndarray, probabilities: np.ndarray, calibration_bins: int) -> dict[str, object]:
    epsilon = 1e-15
    clipped = np.clip(probabilities, epsilon, 1 - epsilon)
    brier = float(np.mean((probabilities - outcomes) ** 2))
    log_loss = float(-np.mean(outcomes * np.log(clipped) + (1 - outcomes) * np.log(1 - clipped)))
    calibration: list[dict[str, float | int]] = []
    weighted_error = 0.0
    for index in range(calibration_bins):
        lower = index / calibration_bins
        upper = (index + 1) / calibration_bins
        mask = (probabilities >= lower) & (
            probabilities <= upper if index == calibration_bins - 1 else probabilities < upper
        )
        count = int(np.sum(mask))
        if not count:
            continue
        mean_probability = float(np.mean(probabilities[mask]))
        outcome_rate = float(np.mean(outcomes[mask]))
        weighted_error += count * abs(mean_probability - outcome_rate)
        calibration.append({
            "lower": round(lower, 12),
            "upper": round(upper, 12),
            "count": count,
            "mean_probability": round(mean_probability, 12),
            "outcome_rate": round(outcome_rate, 12),
        })
    return {
        "brier_score": round(brier, 12),
        "log_loss": round(log_loss, 12),
        "expected_calibration_error": round(weighted_error / len(outcomes), 12),
        "calibration_bins": calibration,
    }


def evaluate_probability_forecasts(
    sample_ids: Sequence[str],
    outcomes: Sequence[int],
    market_probabilities: Sequence[float],
    model_probabilities: Sequence[float],
    calibration_bins: int = 10,
) -> dict[str, object]:
    """Compare a model with the contemporaneous market probability baseline."""

    ids = list(sample_ids)
    actual = np.asarray(outcomes)
    market = _probabilities(market_probabilities, "market_probabilities")
    model = _probabilities(model_probabilities, "model_probabilities")
    if not ids or any(not isinstance(value, str) or not value.strip() for value in ids):
        raise ValueError("sample_ids must contain non-empty strings")
    if len(set(ids)) != len(ids):
        raise ValueError("sample_ids must be unique")
    if actual.ndim != 1 or len(actual) != len(ids) or len(market) != len(ids) or len(model) != len(ids):
        raise ValueError("ids, outcomes, market probabilities, and model probabilities must align")
    if not np.all(np.isin(actual, [0, 1])):
        raise ValueError("outcomes must be binary values")
    if not isinstance(calibration_bins, int) or isinstance(calibration_bins, bool) or not 2 <= calibration_bins <= 20:
        raise ValueError("calibration_bins must be an integer from 2 through 20")
    actual = actual.astype(float)
    market_score = _score(actual, market, calibration_bins)
    model_score = _score(actual, model, calibration_bins)
    brier_improvement = market_score["brier_score"] - model_score["brier_score"]
    log_loss_improvement = market_score["log_loss"] - model_score["log_loss"]
    return {
        "schema_version": 1,
        "record_type": "binary_probability_model_comparison",
        "implementation": {
            "numpy_version": np.__version__,
            "brier_score": "mean_squared_probability_error",
            "log_loss_clipping_epsilon": 1e-15,
        },
        "sample_count": len(ids),
        "market_baseline": market_score,
        "challenger_model": model_score,
        "comparison": {
            "brier_improvement": round(brier_improvement, 12),
            "log_loss_improvement": round(log_loss_improvement, 12),
            "challenger_dominates_on_brier_and_log_loss": (
                brier_improvement > 0 and log_loss_improvement > 0
            ),
        },
        "samples": [
            {
                "sample_id": sample_id,
                "outcome": int(outcome),
                "market_probability": round(float(market_probability), 12),
                "model_probability": round(float(model_probability), 12),
            }
            for sample_id, outcome, market_probability, model_probability in zip(
                ids, actual, market, model, strict=True
            )
        ],
        "interpretation": "Scoring capability only. Dominating a market baseline does not establish net profitability or authorize trading.",
        "strategy_mining_authorized": False,
        "capital_authorized": False,
    }
