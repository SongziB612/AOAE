import unittest
import numpy as np
from aoae.strategy_sleeve_identity import inspect_sleeve_mixture


class SleeveIdentityTests(unittest.TestCase):
    def test_hand_calculation(self):
        r = inspect_sleeve_mixture([[.1,-.1],[.2,0]])
        self.assertAlmostEqual(r['terminal_wealth'], 1.11)
        np.testing.assert_allclose(r['rows'][1]['pre_return_weights'], [.55,.45])
        self.assertLess(r['maximum_inter_sleeve_transfer'], 1e-14)

    def test_causal(self):
        x = np.random.default_rng(12).uniform(-.1,.1,(30,4))
        y = x.copy(); y[15:] = .9
        a,b = inspect_sleeve_mixture(x), inspect_sleeve_mixture(y)
        self.assertEqual([r['pre_return_weights'] for r in a['rows'][:16]], [r['pre_return_weights'] for r in b['rows'][:16]])

    def test_no_survival_guarantee(self):
        r = inspect_sleeve_mixture(np.full((30,2),-.1))
        self.assertLess(r['terminal_wealth'],.05)

    def test_invalid(self):
        for x in ([], [[-1,0]], [[float('nan'),0]]):
            with self.assertRaises(ValueError):
                inspect_sleeve_mixture(x)
