import unittest

from aoae.state_validation import (
    circular_block_bootstrap_mean_lcb,
    maximum_drawdown,
    select_largest_qualifying_buffer,
    summarize_policy,
)


def _row(edge: float, pnl: float, executable: bool = True) -> dict:
    return {
        "eligible": True,
        "estimated_edge": edge,
        "execution_status": "SIMULATED_REPRICE" if executable else "NO_EXECUTABLE_ASK",
        "delayed_net_pnl": pnl,
    }


class StateValidationTests(unittest.TestCase):
    def test_maximum_drawdown_uses_ordered_equity_curve(self):
        self.assertAlmostEqual(maximum_drawdown([2, -1, -3, 4]), 4)

    def test_policy_counts_attempt_but_zero_pnl_when_liquidity_disappears(self):
        result = summarize_policy([_row(0.1, 2), _row(0.2, 99, executable=False)], 0.05)
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(result["fills"], 1)
        self.assertAlmostEqual(result["total_delayed_net_pnl"], 2)

    def test_unconditional_policy_selects_every_eligible_row(self):
        result = summarize_policy([_row(-1.1, -2), {"eligible": False}], None)
        self.assertEqual(result["attempts"], 1)

    def test_calibration_selects_largest_qualifying_buffer(self):
        rows = [_row(0.11, 1) for _ in range(10)] + [_row(0.03, -0.1) for _ in range(2)]
        selected, _ = select_largest_qualifying_buffer(rows, [0, 0.02, 0.05, 0.1], 10)
        self.assertAlmostEqual(selected, 0.1)

    def test_bootstrap_is_deterministic_and_rejects_empty_input(self):
        first = circular_block_bootstrap_mean_lcb([1, 2, 3, 4], 2, 100, 2201)
        second = circular_block_bootstrap_mean_lcb([1, 2, 3, 4], 2, 100, 2201)
        self.assertEqual(first, second)
        with self.assertRaises(ValueError):
            circular_block_bootstrap_mean_lcb([], 2, 100, 2201)


if __name__ == "__main__":
    unittest.main()
