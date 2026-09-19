import unittest
import numpy as np
import pandas as pd
from aoae.equal_vol_control import equal_vol_weights


class EqualVolControlTests(unittest.TestCase):
    def test_future_invariance_and_no_leverage(self):
        rng = np.random.default_rng(321)
        prices = pd.DataFrame(np.exp(rng.normal(0, .025, (100, 2))).cumprod(axis=0), columns=['A', 'B'])
        before = equal_vol_weights(prices, 70, ('A', 'B'))
        prices.iloc[71:] *= 5
        self.assertEqual(before, equal_vol_weights(prices, 70, ('A', 'B')))
        self.assertEqual(before['A'], before['B'])
        self.assertLessEqual(sum(before.values()), 1.)

    def test_matches_direct_basket_vol(self):
        rng = np.random.default_rng(7)
        prices = pd.DataFrame(np.exp(rng.normal(0, .05, (80, 2))).cumprod(axis=0), columns=['A', 'B'])
        basket = prices.iloc[7:71].pct_change().dropna().mean(axis=1)
        exposure = min(1., .12 / (basket.std(ddof=1) * np.sqrt(252)))
        self.assertAlmostEqual(sum(equal_vol_weights(prices, 70, ('A', 'B')).values()), exposure)

    def test_invalid_window_fails(self):
        prices = pd.DataFrame({'A': [1.] * 80, 'B': [1.] * 80})
        for position in (0, 70, 81):
            with self.assertRaises(ValueError):
                equal_vol_weights(prices, position, ('A', 'B'))
