from __future__ import annotations

from pathlib import Path
import unittest

from aoae.contracts import load_spec
from aoae.experiment import apply_strategy, canonical_json, lagged_reversal_positions, run_experiment


SPEC_PATH = Path(__file__).parents[1] / "research" / "experiments" / "0001-synthetic-mean-reversion" / "spec.json"


class ExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = load_spec(SPEC_PATH)

    def test_run_is_deterministic(self) -> None:
        first = canonical_json(run_experiment(self.spec))
        second = canonical_json(run_experiment(self.spec))
        self.assertEqual(first, second)

    def test_positions_use_only_prior_return(self) -> None:
        positions = lagged_reversal_positions([0.02, -0.03, 0.50])
        self.assertEqual(positions, [0.0, -1.0, 1.0])

    def test_future_return_cannot_change_past_position(self) -> None:
        baseline = lagged_reversal_positions([0.02, -0.03, 0.50])
        shocked = lagged_reversal_positions([0.02, -0.03, -99.0])
        self.assertEqual(baseline, shocked)

    def test_turnover_costs_are_charged(self) -> None:
        applied = apply_strategy([0.01, -0.01, 0.01], cost_bps=5.0)
        self.assertEqual(applied["positions"], [0.0, -1.0, 1.0])
        self.assertAlmostEqual(applied["net_returns"][1], 0.0095)
        self.assertAlmostEqual(applied["net_returns"][2], 0.0090)

    def test_reference_experiment_passes_without_authorizing_capital(self) -> None:
        record = run_experiment(self.spec)
        self.assertEqual(record["decision"], "infrastructure_validated")
        self.assertEqual(record["result"]["status"], "PASS")
        self.assertFalse(record["capital_authorized"])


if __name__ == "__main__":
    unittest.main()
