import unittest
import json
from pathlib import Path
import numpy as np

from aoae.net_expert_allocator import net_expert_weights
from aoae.universal import SyntheticCosts, run_portfolio, two_asset_grid, universal_weights
from aoae.universal_synthetic import generate


class NetExpertTests(unittest.TestCase):
    costs = SyntheticCosts(2, 2, 3, 100, 100, .01)

    def test_small_challenge_independently_audits_and_detects_tampering(self):
        from scripts.run_net_expert_challenge import experiment
        from scripts.audit_net_expert_scores import audit
        config = json.loads((Path(__file__).resolve().parents[1] / 'configs/net_expert_challenge.json').read_text(encoding='utf-8'))
        config.update(periods=30, grid_points=11, seeds=[17], worlds=['permanent_loser', 'trend_reversal'])
        record = experiment(config)
        json.dumps(record, allow_nan=False)
        self.assertEqual(record['costed_variant_evaluations'], 12)
        self.assertEqual(audit(record)['status'], 'PASS')
        row = next(r for r in record['runs'] if r['strategy'] == 'net_scored_up')
        row['executed_weights_including_cash'][0][0] += .1
        with self.assertRaisesRegex(ValueError, 'weight'):
            audit(record)

    def test_zero_cost_mathematical_control_matches_gross_up(self):
        x = generate('high_vol_low_corr', 30, 17)
        grid = two_asset_grid(11)
        gross, _ = universal_weights(x, grid)
        net, _ = net_expert_weights(x, grid, None)
        np.testing.assert_allclose(gross, net, atol=1e-12)

    def test_future_and_current_return_do_not_affect_current_allocation(self):
        x = generate('high_vol_low_corr', 30, 17)
        changed = x.copy()
        changed[15:] *= [1.5, .5]
        grid = two_asset_grid(11)
        a, _ = net_expert_weights(x, grid, self.costs)
        b, _ = net_expert_weights(changed, grid, self.costs)
        np.testing.assert_array_equal(a[:16], b[:16])

    def test_prefix_invariance(self):
        x = generate('relative_mean_reversion', 30, 31)
        grid = two_asset_grid(11)
        a, _ = net_expert_weights(x, grid, self.costs)
        b, _ = net_expert_weights(x[:10], grid, self.costs)
        np.testing.assert_array_equal(a[:10], b)

    def test_single_expert_pays_actual_cost_only_once(self):
        x = generate('high_vol_low_corr', 30, 17)
        grid = np.array([[.5, .5]])
        weights, score = net_expert_weights(x, grid, self.costs)
        allocator = run_portfolio(x, weights, 1, self.costs)
        crp = run_portfolio(x, grid[0], 1, self.costs)
        np.testing.assert_allclose(allocator['wealth'], crp['wealth'], atol=1e-14)
        np.testing.assert_allclose(allocator['fees'], crp['fees'], atol=1e-14)
        self.assertFalse(score['expert_costs_debited_to_allocator'])

    def test_posterior_uses_previous_net_wealth(self):
        x = generate('high_vol_low_corr', 20, 73)
        grid = two_asset_grid(3)
        weights, score = net_expert_weights(x, grid, self.costs)
        previous = np.array([run_portfolio(x[:5], b, 1, self.costs)['wealth'][-1] for b in grid])
        np.testing.assert_allclose(score['posterior'][5], previous / previous.sum(), atol=1e-13)
        np.testing.assert_allclose(weights[0], grid.mean(axis=0))

    def test_invalid_grid_rejected(self):
        with self.assertRaises(ValueError):
            net_expert_weights([[1., 1.]], [[-1., 2.]], self.costs)
