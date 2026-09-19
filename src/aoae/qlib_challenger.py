"""Leakage-controlled data and portfolio helpers for the Qlib ETF challenger."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


FEATURES = (
    "return_21",
    "return_63",
    "return_126",
    "return_252",
    "return_126_skip_21",
    "return_252_skip_21",
    "volatility_21",
    "volatility_63",
    "drawdown_252",
    "volume_ratio_21_63",
)


@dataclass(frozen=True)
class MonthlySamples:
    frame: pd.DataFrame
    execution_dates: pd.Series
    label_realized_dates: pd.Series


def build_monthly_samples(
    open_price: pd.DataFrame,
    close: pd.DataFrame,
    volume: pd.DataFrame,
    risk_assets: tuple[str, ...],
) -> MonthlySamples:
    """Build features at month-end and labels between the next two execution opens."""
    if not open_price.index.equals(close.index) or not close.index.equals(volume.index):
        raise ValueError("price and volume calendars differ")
    if tuple(open_price.columns) != tuple(close.columns) or tuple(close.columns) != tuple(volume.columns):
        raise ValueError("price and volume universes differ")
    if not set(risk_assets).issubset(close.columns):
        raise ValueError("risk assets are missing")

    month_ends = close.groupby(close.index.to_period("M")).tail(1).index
    locations = {date: i for i, date in enumerate(close.index)}
    records: list[dict[str, Any]] = []
    index: list[tuple[pd.Timestamp, str]] = []
    executions: list[pd.Timestamp] = []
    realizations: list[pd.Timestamp | pd.NaT] = []

    for month_number, signal_date in enumerate(month_ends):
        i = locations[signal_date]
        if i < 252 or i + 1 >= len(close):
            continue
        execution = close.index[i + 1]
        next_execution = pd.NaT
        if month_number + 1 < len(month_ends):
            next_signal_i = locations[month_ends[month_number + 1]]
            if next_signal_i + 1 < len(close):
                next_execution = close.index[next_signal_i + 1]

        for symbol in risk_assets:
            daily = close[symbol].iloc[i - 63 : i + 1].pct_change().dropna()
            recent_volume = float(volume[symbol].iloc[i - 20 : i + 1].mean())
            long_volume = float(volume[symbol].iloc[i - 62 : i + 1].mean())
            label = np.nan
            if not pd.isna(next_execution):
                label = float(open_price.at[next_execution, symbol] / open_price.at[execution, symbol] - 1)
            records.append(
                {
                    "return_21": float(close.at[signal_date, symbol] / close[symbol].iloc[i - 21] - 1),
                    "return_63": float(close.at[signal_date, symbol] / close[symbol].iloc[i - 63] - 1),
                    "return_126": float(close.at[signal_date, symbol] / close[symbol].iloc[i - 126] - 1),
                    "return_252": float(close.at[signal_date, symbol] / close[symbol].iloc[i - 252] - 1),
                    "return_126_skip_21": float(close[symbol].iloc[i - 21] / close[symbol].iloc[i - 126] - 1),
                    "return_252_skip_21": float(close[symbol].iloc[i - 21] / close[symbol].iloc[i - 252] - 1),
                    "volatility_21": float(daily.iloc[-21:].std(ddof=1) * np.sqrt(252)),
                    "volatility_63": float(daily.std(ddof=1) * np.sqrt(252)),
                    "drawdown_252": float(close.at[signal_date, symbol] / close[symbol].iloc[i - 251 : i + 1].max() - 1),
                    "volume_ratio_21_63": float(recent_volume / long_volume - 1),
                    "LABEL0": label,
                }
            )
            index.append((signal_date, symbol))
            executions.append(execution)
            realizations.append(next_execution)

    multi_index = pd.MultiIndex.from_tuples(index, names=("datetime", "instrument"))
    plain = pd.DataFrame(records, index=multi_index)
    columns = pd.MultiIndex.from_tuples(
        [("feature", name) for name in FEATURES] + [("label", "LABEL0")]
    )
    plain.columns = columns
    return MonthlySamples(
        frame=plain,
        execution_dates=pd.Series(executions, index=multi_index, name="execution_date"),
        label_realized_dates=pd.Series(realizations, index=multi_index, name="label_realized_date"),
    )


def prediction_schedule(
    predictions: pd.Series,
    execution_dates: pd.Series,
    symbols: tuple[str, ...],
    risk_assets: tuple[str, ...],
    defensive_asset: str,
    top_n: int,
) -> dict[pd.Timestamp, tuple[dict[str, float], dict[str, float], str]]:
    """Convert cross-sectional predictions into a deterministic rebalance schedule."""
    schedule = {}
    for signal_date, scores_at_date in predictions.groupby(level="datetime"):
        scores = {str(symbol): float(value) for (_, symbol), value in scores_at_date.items()}
        ranked = sorted((s for s in risk_assets if scores[s] > 0), key=lambda s: (-scores[s], s))
        selected = ranked[:top_n]
        weights = {symbol: 0.0 for symbol in symbols}
        for symbol in selected:
            weights[symbol] = 1.0 / top_n
        weights[defensive_asset] = 1.0 - sum(weights.values())
        execution = pd.Timestamp(execution_dates.loc[(signal_date, risk_assets[0])])
        schedule[execution] = (weights, scores, pd.Timestamp(signal_date).date().isoformat())
    return schedule


def simulate_schedule(
    open_price: pd.DataFrame,
    close: pd.DataFrame,
    schedule: dict[pd.Timestamp, tuple[dict[str, float], dict[str, float], str]],
    symbols: tuple[str, ...],
    initial_capital: float,
    cost_rate: float,
) -> tuple[pd.Series, list[dict[str, Any]]]:
    quantity = {symbol: 0.0 for symbol in symbols}
    cash = initial_capital
    equity, trades = [], []
    for date in close.index:
        if date in schedule:
            weights, scores, signal_date = schedule[date]
            pre_value = cash + sum(quantity[s] * float(open_price.at[date, s]) for s in symbols)
            old_notional = {s: quantity[s] * float(open_price.at[date, s]) for s in symbols}
            traded = sum(abs(pre_value * weights[s] - old_notional[s]) for s in symbols)
            cost = traded * cost_rate
            investable = pre_value - cost
            quantity = {s: investable * weights[s] / float(open_price.at[date, s]) for s in symbols}
            cash = 0.0
            trades.append(
                {
                    "signal_date": signal_date,
                    "execution_date": date.date().isoformat(),
                    "weights": {s: round(w, 6) for s, w in weights.items() if w},
                    "predictions": {s: round(v, 8) for s, v in scores.items()},
                    "turnover": round(traded / pre_value, 8),
                    "cost_cny": round(cost, 4),
                }
            )
        equity.append(cash + sum(quantity[s] * float(close.at[date, s]) for s in symbols))
    return pd.Series(equity, index=close.index, name="challenger"), trades


def mean_monthly_spearman_ic(predictions: pd.Series, labels: pd.Series) -> tuple[float, int]:
    joined = pd.concat({"prediction": predictions, "label": labels}, axis=1).dropna()
    values = []
    for _, group in joined.groupby(level="datetime"):
        correlation = group["prediction"].corr(group["label"], method="spearman")
        if pd.notna(correlation):
            values.append(float(correlation))
    return (float(np.mean(values)) if values else float("nan"), len(values))
