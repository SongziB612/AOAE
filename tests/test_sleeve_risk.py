import unittest
from scripts.audit_sleeve_risk import describe


class SleeveRiskTests(unittest.TestCase):
    def test_initial_loss_in_drawdown(self):
        result, returns = describe([90, 95], 100)
        self.assertAlmostEqual(result['maximum_drawdown'], -.1)
        self.assertAlmostEqual(result['net_pnl_cny'], -5)
        self.assertAlmostEqual(returns[0], -.1)

    def test_peak_and_tail(self):
        result, _ = describe([110, 88, 100], 100)
        self.assertAlmostEqual(result['maximum_drawdown'], -.2)
        self.assertAlmostEqual(result['observed_tail_mean_loss_95'], .2)
        self.assertIsNone(result['risk_of_ruin_probability'])

    def test_invalid(self):
        for nav in ([], [0], [float('inf')]):
            with self.assertRaises(ValueError):
                describe(nav, 100)
