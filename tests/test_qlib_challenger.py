from __future__ import annotations

import numpy as np
import pandas as pd
import unittest

from aoae.qlib_challenger import build_monthly_samples, prediction_schedule


def synthetic_panels(rows: int = 400):
    index = pd.bdate_range("2020-01-01", periods=rows)
    columns = ["R1", "R2", "D"]
    base = np.arange(rows, dtype=float) + 100.0
    close = pd.DataFrame({c: base * (1 + j / 10) for j, c in enumerate(columns)}, index=index)
    open_price = close + 1.0
    volume = pd.DataFrame({c: np.arange(rows, dtype=float) + 1000 + j for j, c in enumerate(columns)}, index=index)
    return open_price, close, volume


class QlibChallengerTests(unittest.TestCase):
    def test_features_use_signal_date_or_earlier_and_label_uses_future_opens(self):
        open_price, close, volume = synthetic_panels()
        samples = build_monthly_samples(open_price, close, volume, ("R1", "R2"))
        signal_date, symbol = samples.frame.index[0]
        execution = samples.execution_dates.loc[(signal_date, symbol)]
        realization = samples.label_realized_dates.loc[(signal_date, symbol)]

        self.assertGreater(execution, signal_date)
        self.assertGreater(realization, execution)
        expected_return = close.at[signal_date, symbol] / close[symbol].iloc[close.index.get_loc(signal_date) - 21] - 1
        expected_label = open_price.at[realization, symbol] / open_price.at[execution, symbol] - 1
        self.assertEqual(samples.frame.loc[(signal_date, symbol), ("feature", "return_21")], expected_return)
        self.assertEqual(samples.frame.loc[(signal_date, symbol), ("label", "LABEL0")], expected_label)

    def test_positive_top_two_predictions_leave_remainder_defensive(self):
        index = pd.MultiIndex.from_product([[pd.Timestamp("2022-01-31")], ["R1", "R2"]], names=["datetime", "instrument"])
        predictions = pd.Series([0.2, -0.1], index=index)
        executions = pd.Series(pd.Timestamp("2022-02-01"), index=index)
        schedule = prediction_schedule(predictions, executions, ("R1", "R2", "D"), ("R1", "R2"), "D", 2)
        weights = schedule[pd.Timestamp("2022-02-01")][0]
        self.assertEqual(weights, {"R1": 0.5, "R2": 0.0, "D": 0.5})
