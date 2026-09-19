from __future__ import annotations

import unittest

import pandas as pd

from aoae.etf_momentum import MomentumSpec
from aoae.etf_validation import independent_targets, period_stats


class ETFValidationTests(unittest.TestCase):
    def test_independent_signal_does_not_use_signal_day_or_future(self) -> None:
        index = pd.bdate_range("2020-01-01", periods=310)
        close = pd.DataFrame({"a": range(100, 410), "b": [100.0] * 310, "d": [100.0] * 310}, index=index)
        spec = MomentumSpec(("a", "b", "d"), ("a", "b"), "d", "a", (126, 252), 21, 2, 0.0015, 100000, "2021-01-01", "2021-12-31")
        first = independent_targets(close, spec)
        close.iloc[-1, 0] = 1_000_000
        second = independent_targets(close, spec)
        pd.testing.assert_frame_equal(first, second)

    def test_period_stats_known_return_and_drawdown(self) -> None:
        equity = pd.Series([100.0, 120.0, 90.0, 110.0], index=pd.date_range("2024-01-01", periods=4))
        result = period_stats(equity)
        self.assertEqual(result["total_return"], 0.1)
        self.assertEqual(result["max_drawdown"], -0.25)


if __name__ == "__main__":
    unittest.main()
