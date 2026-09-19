from __future__ import annotations

import unittest

import pandas as pd

from aoae.etf_momentum import MomentumSpec, score_at, target_weights


def spec() -> MomentumSpec:
    return MomentumSpec(("a", "b", "d"), ("a", "b"), "d", "a", (4, 6), 1, 2, 0.0015, 100_000, "2022-01-01", "2022-12-31")


class ETFMomentumTests(unittest.TestCase):
    def test_score_skips_most_recent_observation(self) -> None:
        frame = pd.DataFrame({"a": [10, 10, 10, 10, 12, 14, 999], "b": [10] * 7, "d": [10] * 7})
        scores = score_at(frame, 6, spec())
        self.assertAlmostEqual(scores["a"], ((14 / 10 - 1) + (14 / 10 - 1)) / 2)

    def test_only_positive_assets_are_selected(self) -> None:
        weights = target_weights({"a": 0.2, "b": -0.1}, spec())
        self.assertEqual(weights, {"a": 0.5, "b": 0.0, "d": 0.5})

    def test_all_negative_moves_fully_defensive(self) -> None:
        weights = target_weights({"a": -0.2, "b": 0.0}, spec())
        self.assertEqual(weights["d"], 1.0)


if __name__ == "__main__":
    unittest.main()
