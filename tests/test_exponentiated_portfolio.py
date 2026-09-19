import unittest
import numpy as np
from aoae.exponentiated_portfolio import eg_weights


class EGTests(unittest.TestCase):
    def test_hand_calculation(self):
        actual = eg_weights([[1.1, .9], [1, 1]], .1)
        expected = np.exp([.11, .09]); expected /= expected.sum()
        np.testing.assert_allclose(actual[0], [.5, .5])
        np.testing.assert_allclose(actual[1], expected)

    def test_future_does_not_change_past(self):
        x = np.random.default_rng(17).uniform(.8, 1.2, (40, 2))
        y = x.copy(); y[20:] = [2, .01]
        np.testing.assert_array_equal(eg_weights(x, .1)[:21], eg_weights(y, .1)[:21])

    def test_zero_is_equal_and_scale_invariant(self):
        x = np.array([[1.1, .8], [.7, 1.2]])
        np.testing.assert_allclose(eg_weights(x, 0), .5)
        np.testing.assert_allclose(eg_weights(x, .1), eg_weights(x * [[100], [.01]], .1))

    def test_invalid(self):
        for eta in (-1, float('inf'), float('nan')):
            with self.assertRaises(ValueError):
                eg_weights([[1, 1]], eta)
