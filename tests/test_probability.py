from __future__ import annotations

import unittest

from aoae.probability import evaluate_probability_forecasts, market_anchored_probabilities


class ProbabilityEvaluationTests(unittest.TestCase):
    def test_zero_adjustment_reproduces_market(self) -> None:
        probabilities = market_anchored_probabilities([0.2, 0.5, 0.8], [0, 0, 0], 1.0)
        self.assertEqual(probabilities, [0.2, 0.5, 0.8])

    def test_adjustment_is_capped(self) -> None:
        capped = market_anchored_probabilities([0.5], [100], 1.0)
        explicit = market_anchored_probabilities([0.5], [1], 1.0)
        self.assertEqual(capped, explicit)

    def test_informative_challenger_beats_uninformative_market(self) -> None:
        record = evaluate_probability_forecasts(
            ["a", "b", "c", "d"],
            [0, 0, 1, 1],
            [0.5, 0.5, 0.5, 0.5],
            [0.1, 0.2, 0.8, 0.9],
            calibration_bins=5,
        )
        self.assertTrue(record["comparison"]["challenger_dominates_on_brier_and_log_loss"])
        self.assertFalse(record["strategy_mining_authorized"])
        self.assertFalse(record["capital_authorized"])

    def test_overconfident_wrong_model_is_penalized(self) -> None:
        record = evaluate_probability_forecasts(
            ["a", "b"], [0, 1], [0.4, 0.6], [0.99, 0.01], calibration_bins=2
        )
        self.assertLess(record["comparison"]["log_loss_improvement"], 0)

    def test_invalid_probabilities_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, r"in \[0, 1\]"):
            evaluate_probability_forecasts(["a"], [1], [1.1], [0.9])


if __name__ == "__main__":
    unittest.main()
