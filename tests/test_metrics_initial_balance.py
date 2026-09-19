import unittest

import pandas as pd

from aoae.etf_momentum import metrics


class InitialBalanceTests(unittest.TestCase):
    def test_initial_loss_counts_as_drawdown(self):
        equity = pd.Series([90., 95.], index=pd.to_datetime(['2024-01-02', '2025-01-02']))
        self.assertAlmostEqual(metrics(equity, 100.)['max_drawdown'], -0.1)

    def test_later_peak_still_counts(self):
        equity = pd.Series([90., 120., 96.], index=pd.to_datetime(['2024-01-02', '2024-06-02', '2025-01-02']))
        self.assertAlmostEqual(metrics(equity, 100.)['max_drawdown'], -0.2)

    def test_no_explicit_baseline_preserves_first_observation(self):
        equity = pd.Series([90., 95.], index=pd.to_datetime(['2024-01-02', '2025-01-02']))
        self.assertEqual(metrics(equity)['max_drawdown'], 0.)
