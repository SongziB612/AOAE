"""Deterministic reference experiment for validating the research pipeline."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import random
from typing import Any, Sequence

from aoae.contracts import ExperimentSpec


def generate_paired_ar1(spec: ExperimentSpec) -> dict[str, list[float]]:
    """Generate paired series from identical innovations, changing only phi."""
    rng = random.Random(spec.data.seed)
    innovations = [rng.gauss(0.0, spec.data.sigma) for _ in range(spec.data.samples)]

    def series(phi: float) -> list[float]:
        previous = 0.0
        values: list[float] = []
        for innovation in innovations:
            current = phi * previous + innovation
            values.append(current)
            previous = current
        return values

    return {
        "structured": series(spec.data.structured_phi),
        "control": series(spec.data.control_phi),
    }


def lagged_reversal_positions(returns: Sequence[float]) -> list[float]:
    """Choose position t from return t-1 only; position 0 is flat."""
    positions = [0.0]
    for previous_return in returns[:-1]:
        if previous_return > 0:
            positions.append(-1.0)
        elif previous_return < 0:
            positions.append(1.0)
        else:
            positions.append(0.0)
    return positions


def apply_strategy(returns: Sequence[float], cost_bps: float) -> dict[str, list[float]]:
    positions = lagged_reversal_positions(returns)
    cost_rate = cost_bps / 10_000.0
    gross_returns: list[float] = []
    net_returns: list[float] = []
    turnovers: list[float] = []
    costs: list[float] = []
    previous_position = 0.0

    for market_return, position in zip(returns, positions, strict=True):
        turnover = abs(position - previous_position)
        transaction_cost = turnover * cost_rate
        gross_return = position * market_return
        gross_returns.append(gross_return)
        net_returns.append(gross_return - transaction_cost)
        turnovers.append(turnover)
        costs.append(transaction_cost)
        previous_position = position

    return {
        "positions": positions,
        "gross_returns": gross_returns,
        "net_returns": net_returns,
        "turnovers": turnovers,
        "costs": costs,
    }


def _rounded(value: float) -> float:
    return round(value, 12)


def calculate_metrics(
    gross_returns: Sequence[float],
    net_returns: Sequence[float],
    turnovers: Sequence[float],
    costs: Sequence[float],
    annualization_periods: int,
) -> dict[str, int | float]:
    count = len(net_returns)
    if not count or not (len(gross_returns) == len(turnovers) == len(costs) == count):
        raise ValueError("metric inputs must be non-empty and have equal lengths")

    mean_gross = math.fsum(gross_returns) / count
    mean_net = math.fsum(net_returns) / count
    variance = math.fsum((value - mean_net) ** 2 for value in net_returns) / max(count - 1, 1)
    volatility = math.sqrt(variance)
    annualized_sharpe = 0.0 if volatility == 0 else mean_net / volatility * math.sqrt(annualization_periods)

    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for period_return in net_returns:
        equity *= 1.0 + period_return
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity / peak - 1.0)

    return {
        "observations": count,
        "mean_gross_return": _rounded(mean_gross),
        "mean_net_return": _rounded(mean_net),
        "net_volatility": _rounded(volatility),
        "annualized_sharpe": _rounded(annualized_sharpe),
        "cumulative_net_return": _rounded(equity - 1.0),
        "max_drawdown": _rounded(max_drawdown),
        "turnover": _rounded(math.fsum(turnovers)),
        "transaction_cost": _rounded(math.fsum(costs)),
    }


def _segment_metrics(
    applied: dict[str, list[float]],
    start: int,
    end: int,
    annualization_periods: int,
) -> dict[str, int | float]:
    return calculate_metrics(
        applied["gross_returns"][start:end],
        applied["net_returns"][start:end],
        applied["turnovers"][start:end],
        applied["costs"][start:end],
        annualization_periods,
    )


def run_experiment(spec: ExperimentSpec) -> dict[str, Any]:
    paired_returns = generate_paired_ar1(spec)
    split_index = int(spec.data.samples * spec.method.train_fraction)
    metrics: dict[str, dict[str, dict[str, int | float]]] = {}

    for label, returns in paired_returns.items():
        applied = apply_strategy(returns, spec.method.cost_bps)
        metrics[label] = {
            "in_sample": _segment_metrics(applied, 0, split_index, spec.method.annualization_periods),
            "out_of_sample": _segment_metrics(
                applied,
                split_index,
                spec.data.samples,
                spec.method.annualization_periods,
            ),
        }

    structured_oos = metrics["structured"]["out_of_sample"]
    control_oos = metrics["control"]["out_of_sample"]
    return_check = bool(
        structured_oos["cumulative_net_return"]
        > spec.decision_rule.min_structured_oos_cumulative_return
    )
    comparison_check = bool(
        structured_oos["mean_net_return"] > control_oos["mean_net_return"]
    )
    if not spec.decision_rule.require_structured_oos_mean_above_control:
        comparison_check = True
    passed = return_check and comparison_check

    return {
        "schema_version": 1,
        "experiment_id": spec.experiment_id,
        "record_type": "synthetic_infrastructure_smoke_test",
        "hypothesis": spec.hypothesis,
        "evidence": {
            "data": {
                "kind": spec.data.kind,
                "paired_innovations": True,
                "seed": spec.data.seed,
                "samples": spec.data.samples,
                "structured_phi": spec.data.structured_phi,
                "control_phi": spec.data.control_phi,
                "sigma": spec.data.sigma,
            },
            "metrics": metrics,
        },
        "method": {
            "strategy": spec.method.strategy,
            "signal_lag": spec.method.signal_lag,
            "split": {
                "kind": "contiguous_preregistered",
                "train_end_exclusive": split_index,
                "out_of_sample_start_inclusive": split_index,
            },
            "cost_bps_per_unit_turnover": spec.method.cost_bps,
            "annualization_periods": spec.method.annualization_periods,
            "trial_count": spec.method.trial_count,
            "bias_controls": list(spec.bias_controls),
        },
        "result": {
            "status": "PASS" if passed else "FAIL",
            "checks": {
                "structured_oos_cumulative_return_above_minimum": return_check,
                "structured_oos_mean_return_above_control": comparison_check,
            },
            "interpretation": (
                "The deterministic runner recovered the deliberately injected structure out of sample. "
                "This validates only the experiment plumbing, not a market edge."
                if passed
                else "The reference runner failed its preregistered synthetic-data checks."
            ),
        },
        "failure_modes": list(spec.failure_modes),
        "confidence": spec.confidence,
        "decision": "infrastructure_validated" if passed else "infrastructure_failed",
        "capital_authorized": spec.capital_authorized,
        "next_experiment": spec.next_experiment,
    }


def canonical_json(record: dict[str, Any]) -> str:
    return json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def record_digest(record_text: str) -> str:
    return hashlib.sha256(record_text.encode("utf-8")).hexdigest()


def write_record(path: Path, record: dict[str, Any], replace: bool = False) -> str:
    if path.exists() and not replace:
        raise FileExistsError(f"refusing to overwrite existing record: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = canonical_json(record)
    path.write_text(text, encoding="utf-8", newline="\n")
    return record_digest(text)
