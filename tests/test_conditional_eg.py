import unittest
import numpy as np
from aoae.conditional_eg import lagged_volatility_states, conditional_weights
from aoae.exponentiated_portfolio import eg_weights


class ConditionalEGTests(unittest.TestCase):
    def test_constant_state_matches_plain(self):
        x = np.random.default_rng(12).uniform(.9, 1.1, (40, 2))
        np.testing.assert_allclose(conditional_weights(x, [0]*40, .05), eg_weights(x, .05))

    def test_future_perturbation(self):
        x = np.random.default_rng(13).uniform(.9, 1.1, (40, 2))
        y = x.copy(); y[25:] = [.01, 2]
        a = lagged_volatility_states(x, 5, .02)
        b = lagged_volatility_states(y, 5, .02)
        np.testing.assert_array_equal(a[:26], b[:26])
        np.testing.assert_array_equal(conditional_weights(x, a, .05)[:26], conditional_weights(y, b, .05)[:26])

    def test_state_bank_retains_only_own_observations(self):
        x = np.array([[1.1,.9],[.5,2],[1,1]])
        actual = conditional_weights(x, [0,1,0], .05)
        np.testing.assert_allclose(actual[1], [.5,.5])
        np.testing.assert_allclose(actual[2], eg_weights(x[[0,2]], .05)[1])

    def test_invalid_state(self):
        with self.assertRaises(ValueError):
            conditional_weights([[1,1]], [2], .05)
