from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from aoae.etf_momentum import MomentumSpec
from aoae.etf_risk_overlay import overlay_weights


class ETFRiskOverlayTests(unittest.TestCase):
    def setUp(self):
        self.spec = MomentumSpec(
            symbols=("A", "B", "D"), risk_assets=("A", "B"), defensive_asset="D", benchmark="A",
            windows=(126, 252), skip=21, top_n=2, cost_rate=0.0015, initial_capital=100000,
            holdout_start="2022-01-01", holdout_end="2026-08-31",
        )
        index = pd.bdate_range("2020-01-01", periods=320)
        rng = np.random.default_rng(7)
        a = 100 * np.exp(np.cumsum(0.001 + rng.normal(0, 0.02, len(index))))
        b = 100 * np.exp(np.cumsum(0.001 + rng.normal(0, 0.006, len(index))))
        self.close = pd.DataFrame({"A": a, "B": b, "D": np.linspace(100, 102, len(index))}, index=index)

    def test_overlay_sums_to_one_and_never_exceeds_base_risk(self):
        weights, _, diagnostics = overlay_weights(self.close, 319, self.spec)
        self.assertAlmostEqual(sum(weights.values()), 1.0)
        self.assertLessEqual(diagnostics["risk_exposure"], 1.0)
        self.assertGreaterEqual(weights["D"], 0.0)

    def test_higher_volatility_asset_gets_lower_selected_weight(self):
        weights, _, _ = overlay_weights(self.close, 319, self.spec)
        if weights["A"] > 0 and weights["B"] > 0:
            self.assertLess(weights["A"], weights["B"])

    def test_future_prices_cannot_change_past_overlay(self):
        original = overlay_weights(self.close, 300, self.spec)[0]
        changed = self.close.copy()
        changed.iloc[301:, :2] *= 10
        self.assertEqual(original, overlay_weights(changed, 300, self.spec)[0])
