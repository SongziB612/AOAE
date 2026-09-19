from pathlib import Path
import unittest
import numpy as np
import pandas as pd

from aoae.etf_momentum import load_spec
from aoae.forward_signal import ARMS, frozen_weights


class ForwardSignalTests(unittest.TestCase):
    def setUp(self):
        self.spec = load_spec(Path(__file__).resolve().parents[1] / 'research/hypotheses/0004-cn-etf-dual-momentum/spec.json')
        dates = pd.bdate_range('2024-01-01', periods=310)
        t = np.arange(len(dates))
        self.panel = pd.DataFrame({s: np.exp(.0004 * (i + 1) * t + .005 * np.sin(t / (i + 2))) for i, s in enumerate(self.spec.symbols)}, index=dates)

    def test_future_prices_do_not_change_signal(self):
        day = self.panel.index[280]
        expected = frozen_weights(self.panel, [], self.spec, day)
        self.panel.iloc[281:] *= 1000
        self.assertEqual(expected, frozen_weights(self.panel, [], self.spec, day))

    def test_five_assets_cash_and_exposure_match(self):
        result = frozen_weights(self.panel, [], self.spec, self.panel.index[-1])
        self.assertEqual(set(result['weights']), set(ARMS))
        for arm, weights in result['weights'].items():
            self.assertEqual(set(weights), set(self.spec.risk_assets))
            self.assertAlmostEqual(sum(weights.values()) + result['cash_weights'][arm], 1.)
        self.assertAlmostEqual(sum(result['weights'][ARMS[0]].values()), sum(result['weights'][ARMS[2]].values()))

    def test_insufficient_history_rejected(self):
        with self.assertRaises(ValueError):
            frozen_weights(self.panel, [], self.spec, self.panel.index[50])
