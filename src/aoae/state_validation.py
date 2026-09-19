"""Deterministic scoring utilities for the preregistered state validation."""

from __future__ import annotations

from typing import Any, Iterable

import numpy as np


def maximum_drawdown(pnls: Iterable[float]) -> float:
    """Return the largest peak-to-trough loss of an ordered PnL stream."""
    equity = 0.0
    peak = 0.0
    drawdown = 0.0
    for pnl in pnls:
        equity += float(pnl)
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def circular_block_bootstrap_mean_lcb(
    values: Iterable[float],
    block_length: int,
    draws: int,
    seed: int,
    alpha: float = 0.05,
) -> float:
    """Lower two-sided confidence bound for the mean via circular blocks."""
    series = np.asarray(list(values), dtype=float)
    if series.size == 0 or block_length <= 0 or draws <= 0 or not 0 < alpha < 1:
        raise ValueError("invalid bootstrap inputs")
    rng = np.random.default_rng(seed)
    blocks_needed = int(np.ceil(series.size / block_length))
    means = np.empty(draws, dtype=float)
    offsets = np.arange(block_length)
    for draw in range(draws):
        starts = rng.integers(0, series.size, size=blocks_needed)
        indices = (starts[:, None] + offsets) % series.size
        sample = series[indices.ravel()[: series.size]]
        means[draw] = float(sample.mean())
    return float(np.quantile(means, alpha / 2))


def summarize_policy(rows: list[dict[str, Any]], buffer: float | None) -> dict[str, Any]:
    """Score a frozen edge threshold; missing delayed liquidity earns zero PnL."""
    market_pnls: list[float] = []
    attempts = 0
    fills = 0
    for row in rows:
        selected = bool(row.get("eligible")) and (
            buffer is None or float(row["estimated_edge"]) > float(buffer)
        )
        if selected:
            attempts += 1
        filled = selected and row.get("execution_status") == "SIMULATED_REPRICE"
        if filled:
            fills += 1
        market_pnls.append(float(row["delayed_net_pnl"]) if filled else 0.0)
    return {
        "buffer": float(buffer) if buffer is not None else None,
        "attempts": attempts,
        "fills": fills,
        "fill_rate_per_attempt": fills / attempts if attempts else 0.0,
        "total_delayed_net_pnl": float(sum(market_pnls)),
        "mean_pnl_per_market": float(np.mean(market_pnls)) if market_pnls else 0.0,
        "maximum_drawdown": maximum_drawdown(market_pnls),
        "market_pnls": market_pnls,
    }


def select_largest_qualifying_buffer(
    rows: list[dict[str, Any]], buffers: Iterable[float], minimum_attempts: int
) -> tuple[float | None, list[dict[str, Any]]]:
    """Apply the preregistered calibration rule without consulting holdout data."""
    summaries = [summarize_policy(rows, value) for value in buffers]
    qualifying = [
        item
        for item in summaries
        if item["attempts"] >= minimum_attempts and item["total_delayed_net_pnl"] > 0
    ]
    selected = max((item["buffer"] for item in qualifying), default=None)
    return selected, summaries
