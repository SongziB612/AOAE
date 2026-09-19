import unittest

from aoae.edge_portfolio import allocate_edges, assess_edge


def edge(edge_id="x", **updates):
    value = {
        "edge_id": edge_id,
        "strategy_family": "family",
        "mechanism": "test",
        "evidence_state": "FORWARD_EXECUTION_VALIDATED",
        "minimum_forward_observations": 100,
        "forward_observations": 100,
        "forward_net_pnl_after_costs": 10,
        "selection_adjusted_mean_pnl_lcb": .01,
        "selection_bias_accounted": True,
        "independent_audit_passed": True,
        "execution_attempts": 100,
        "execution_fills": 90,
        "minimum_execution_fill_rate": .8,
        "execution_reconciled": True,
        "estimated_capacity_cny": 10000,
        "risk_limit_breached": False,
        "forward_only": True,
        "maximum_allocation_fraction": .25,
    }
    value.update(updates)
    return value


class EdgePortfolioTests(unittest.TestCase):
    def test_positive_backtest_without_forward_evidence_is_rejected(self):
        result = assess_edge(edge(forward_observations=0, forward_only=False))
        self.assertFalse(result["admitted_to_autonomous_portfolio"])
        self.assertIn("minimum_forward_observations", result["failed_checks"])

    def test_negative_adjusted_bound_is_rejected(self):
        self.assertFalse(assess_edge(edge(selection_adjusted_mean_pnl_lcb=-.01))["admitted_to_autonomous_portfolio"])

    def test_no_admitted_edge_forces_all_cash(self):
        result = allocate_edges([edge(forward_observations=0)], .5)
        self.assertEqual(result["allocations"], {"cash": 1.0})
        self.assertFalse(result["autonomous_portfolio_ready"])

    def test_admitted_edges_are_capped_without_leverage(self):
        result = allocate_edges([edge("a"), edge("b")], .4)
        self.assertAlmostEqual(result["allocations"]["a"], .2)
        self.assertAlmostEqual(result["allocations"]["b"], .2)
        self.assertAlmostEqual(result["allocations"]["cash"], .6)
        self.assertFalse(result["leverage_allowed"])


if __name__ == "__main__":
    unittest.main()
