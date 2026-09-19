from __future__ import annotations

import unittest

import pandas as pd

from aoae.small_account import cap_risk_weights, execution_cost, order_cost, target_lots


class SmallAccountTests(unittest.TestCase):
    def test_risk_cap_only_scales_down(self):
        self.assertEqual(cap_risk_weights({"A": 0.2, "B": 0.1}, ("A", "B"), 0.4), {"A": 0.2, "B": 0.1})
        scaled = cap_risk_weights({"A": 0.6, "B": 0.4}, ("A", "B"), 0.4)
        self.assertAlmostEqual(scaled["A"], 0.24)
        self.assertAlmostEqual(scaled["B"], 0.16)

    def test_minimum_order_cost_is_applied(self):
        self.assertEqual(order_cost(300, 0.0015, 5), 5)
        self.assertEqual(order_cost(10000, 0.0015, 5), 15)
        self.assertEqual(order_cost(0, 0.0015, 5), 0)

    def test_slippage_is_separate_from_commission(self):
        self.assertEqual(execution_cost(1000, 0.003, 5, 30), 8)
        with self.assertRaisesRegex(ValueError, "slippage"):
            execution_cost(1000, 0.003, 5, -1)

    def test_targets_round_down_to_100_share_lots(self):
        prices = pd.Series({"A": 3.45, "B": 2.71})
        targets = target_lots(10000, {"A": 0.1, "B": 0.3}, prices, 100)
        self.assertEqual(targets, {"A": 200, "B": 1100})
