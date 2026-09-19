from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from aoae.etf_momentum import MomentumSpec
from aoae.etf_risk_overlay import build_overlay_schedule
from aoae.etf_risk_validation import independent_overlay_targets


class ETFRiskValidationTests(unittest.TestCase):
    def test_independent_targets_match_production_weights(self):
        index = pd.bdate_range("2019-01-01", periods=700)
        rng = np.random.default_rng(11)
        close = pd.DataFrame({
            "A": 100 * np.exp(np.cumsum(0.0008 + rng.normal(0, 0.012, len(index)))),
            "B": 100 * np.exp(np.cumsum(0.0006 + rng.normal(0, 0.007, len(index)))),
            "D": 100 * np.exp(np.cumsum(0.0001 + rng.normal(0, 0.001, len(index)))),
        }, index=index)
        spec = MomentumSpec(
            symbols=("A", "B", "D"), risk_assets=("A", "B"), defensive_asset="D", benchmark="A",
            windows=(126, 252), skip=21, top_n=2, cost_rate=0.0015, initial_capital=100000,
            holdout_start="2022-01-01", holdout_end="2026-08-31",
        )
        independent = independent_overlay_targets(close, spec, 63, 0.12).dropna(how="all")
        production = build_overlay_schedule(close, spec, 63, 0.12)
        for date, row in independent.iterrows():
            expected = production[date][0]
            for symbol in spec.symbols:
                self.assertAlmostEqual(row[symbol], expected[symbol], places=12)
