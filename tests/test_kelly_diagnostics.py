import itertools
import math
import unittest

from aoae.kelly_diagnostics import binary_diagnostic


class KellyDiagnosticTests(unittest.TestCase):
    def test_small_path_enumeration_independent(self):
        p, b, f, n, barrier = .55, 2, .25, 10, .5
        terminal = hit = 0.0
        for path in itertools.product((False, True), repeat=n):
            wealth, probability, breached = 1.0, 1.0, False
            for won in path:
                wealth *= 1 + f * b if won else 1 - f
                probability *= p if won else 1 - p
                breached |= wealth <= barrier
            terminal += probability * (wealth < 1)
            hit += probability * breached
        result = binary_diagnostic(p, b, f, n, barrier)
        self.assertAlmostEqual(result['terminal_loss_probability'], terminal)
        self.assertAlmostEqual(result['ever_barrier_probability'], hit)
        self.assertLess(result['probability_mass_error'], 1e-13)

    def test_hand_calculation(self):
        result = binary_diagnostic(.5, 1, .5, 2, .3)
        self.assertAlmostEqual(result['terminal_loss_probability'], .75)
        self.assertAlmostEqual(result['ever_barrier_probability'], .25)

    def test_kelly_and_half_variance(self):
        full = binary_diagnostic(.55, 2, .325)
        half = binary_diagnostic(.55, 2, .1625)
        self.assertAlmostEqual(full['long_only_kelly_fraction'], .325)
        self.assertAlmostEqual(half['simple_return_variance'] / full['simple_return_variance'], .25)
        self.assertGreater(full['expected_log_growth_per_bet'], half['expected_log_growth_per_bet'])
        self.assertGreater(half['ever_barrier_probability'], 0)

    def test_zero_and_no_edge(self):
        self.assertEqual(binary_diagnostic(.55, 2, 0)['terminal_loss_probability'], 0)
        self.assertEqual(binary_diagnostic(.2, 2, .1625)['long_only_kelly_fraction'], 0)
        self.assertLess(binary_diagnostic(.2, 2, .1625)['expected_log_growth_per_bet'], 0)
        self.assertEqual(binary_diagnostic(0, 2, .25)['ever_barrier_probability'], 1)
        self.assertEqual(binary_diagnostic(1, 2, .25)['ever_barrier_probability'], 0)

    def test_invalid(self):
        for f in (-.1, 1, math.nan):
            with self.assertRaises(ValueError):
                binary_diagnostic(.55, 2, f)
