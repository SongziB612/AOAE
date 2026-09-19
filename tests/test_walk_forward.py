from __future__ import annotations

import unittest

from aoae.walk_forward import WalkForwardConfig, evaluate_walk_forward


def config(**overrides: object) -> WalkForwardConfig:
    values = {
        "n_splits": 3,
        "test_size": 20,
        "gap": 5,
        "target_horizon_observations": 5,
        "minimum_train_size": 100,
        "ridge_alpha": 1.0,
    }
    values.update(overrides)
    return WalkForwardConfig(**values)


class WalkForwardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.features = [[float(index), float(index % 7)] for index in range(180)]
        self.targets = [2.0 * row[0] - 0.5 * row[1] + 3.0 for row in self.features]

    def test_gap_must_cover_target_horizon(self) -> None:
        with self.assertRaisesRegex(ValueError, "full target horizon"):
            evaluate_walk_forward(self.features, self.targets, config(gap=4))

    def test_splits_are_ordered_and_gap_is_recorded(self) -> None:
        record = evaluate_walk_forward(self.features, self.targets, config())
        for fold in record["folds"]:
            self.assertLess(fold["train_end"], fold["test_start"])
            self.assertEqual(fold["gap_size"], 5)
        self.assertEqual(record["sample"]["out_of_sample_predictions"], 60)

    def test_ridge_beats_train_mean_on_linear_fixture(self) -> None:
        record = evaluate_walk_forward(self.features, self.targets, config())
        self.assertTrue(record["aggregate"]["model_beats_baseline_on_mae_and_rmse"])
        self.assertGreater(record["aggregate"]["model_metrics"]["correlation"], 0.99)
        self.assertFalse(record["strategy_mining_authorized"])
        self.assertFalse(record["capital_authorized"])

    def test_evaluation_is_deterministic(self) -> None:
        first = evaluate_walk_forward(self.features, self.targets, config())
        second = evaluate_walk_forward(self.features, self.targets, config())
        self.assertEqual(first, second)

    def test_future_targets_cannot_change_first_fold_predictions(self) -> None:
        original = evaluate_walk_forward(self.features, self.targets, config())
        changed_targets = list(self.targets)
        changed_targets[140:] = [value + 10000 for value in changed_targets[140:]]
        changed = evaluate_walk_forward(self.features, changed_targets, config())
        original_first = [row for row in original["predictions"] if row["index"] < 140]
        changed_first = [row for row in changed["predictions"] if row["index"] < 140]
        self.assertEqual(original_first, changed_first)

    def test_future_features_cannot_change_first_fold_predictions(self) -> None:
        original = evaluate_walk_forward(self.features, self.targets, config())
        changed_features = [list(row) for row in self.features]
        changed_features[140:] = [[value * 10000 for value in row] for row in changed_features[140:]]
        changed = evaluate_walk_forward(changed_features, self.targets, config())
        original_first = [row for row in original["predictions"] if row["index"] < 140]
        changed_first = [row for row in changed["predictions"] if row["index"] < 140]
        self.assertEqual(original_first, changed_first)


if __name__ == "__main__":
    unittest.main()
