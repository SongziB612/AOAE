import unittest
import json
from pathlib import Path
import numpy as np

from aoae.universal import SyntheticCosts, bcrp, relatives, run_portfolio, two_asset_grid, universal_weights
from aoae.universal_metrics import decomposition, metrics
from aoae.universal_synthetic import generate


class UniversalTests(unittest.TestCase):
    def test_small_suite_serializes_without_nan(self):
        from scripts.run_universal_baselines import experiment
        config = json.loads((Path(__file__).resolve().parents[1] / 'configs/universal_synthetic.json').read_text(encoding='utf-8'))
        config.update(periods=30, seeds=[17], grid_points=11)
        result = experiment(config)
        result['config'] = config
        self.assertEqual(result['costed_variant_evaluations'], 98)
        self.assertIsInstance(json.dumps(result, allow_nan=False), str)
        from scripts.audit_universal_baselines import audit
        self.assertEqual(audit(result)['status'], 'PASS')
        result['runs'][0]['turnover_path'][0] += .01
        with self.assertRaisesRegex(ValueError, 'participation mismatch'):
            audit(result)

    def test_buy_hold_identity(self):
        x = np.array([[2., .5], [.5, 2.]])
        self.assertAlmostEqual(run_portfolio(x, [.5, .5], None)['wealth'][-1], 1.)
        self.assertAlmostEqual(run_portfolio(x, [.5, .5], 1)['wealth'][-1], 1.5625)

    def test_universal_identity(self):
        x = generate('high_vol_low_corr', 40, 2)
        grid = two_asset_grid(31)
        weights, expected_log = universal_weights(x, grid)
        self.assertAlmostEqual(np.log(run_portfolio(x, weights)['wealth'][-1]), expected_log, places=11)
        self.assertAlmostEqual(np.exp(expected_log), np.prod(x @ grid.T, axis=0).mean(), places=11)

    def test_future_mutation_cannot_change_current_weights(self):
        x = generate('high_vol_low_corr', 40, 5)
        altered = x.copy()
        altered[20:] *= [3., .2]
        grid = two_asset_grid(21)
        before, _ = universal_weights(x, grid)
        after, _ = universal_weights(altered, grid)
        np.testing.assert_array_equal(before[:21], after[:21])

    def test_prefix_invariance(self):
        x = generate('relative_mean_reversion', 60, 8)
        grid = two_asset_grid(11)
        full, _ = universal_weights(x, grid)
        short, _ = universal_weights(x[:20], grid)
        np.testing.assert_array_equal(full[:20], short)

    def test_bcrp_symmetric_interior(self):
        fit = bcrp([[2., .5], [.5, 2.]])
        np.testing.assert_allclose(fit['weights'], [.5, .5], atol=1e-7)

    def test_bcrp_trend_boundary_and_label(self):
        fit = bcrp(np.tile([1.02, .99], (50, 1)))
        self.assertGreater(fit['weights'][0], .99999)
        self.assertEqual(fit['information_class'], 'EX_POST_OPTIMUM')

    def test_diversification_is_not_profit(self):
        d = decomposition(generate('permanent_loser', 252, 1), np.array([.5, .5]))
        self.assertGreater(d['exact_diversification_log_growth'], 0)
        self.assertLess(d['crp_log_growth'], 0)
        self.assertLess(d['rebalancing_log_premium_vs_same_weight_buy_hold'], 0)

    def test_flat_assets_pay_initial_cost_only(self):
        costs = SyntheticCosts(2, 2, 3, 100, 100, .01)
        run = run_portfolio(np.ones((10, 2)), [.5, .5], None, costs)
        self.assertAlmostEqual(run['wealth'][-1], 1 / (1 + costs.rate))
        self.assertEqual(run['trade_legs'], 2)
        self.assertGreater(run['fees'][0], 0)

    def test_capacity_leaves_cash_and_never_exceeds_cap(self):
        costs = SyntheticCosts(2, 2, 3, 100, 1, .01)
        run = run_portfolio(np.ones((5, 2)), [.5, .5], 1, costs)
        self.assertTrue(np.all(run['turnover'] <= .01 + 1e-10))
        self.assertGreater(run['executed_weights_including_cash'][0, -1], .98)

    def test_self_financing_independent_period_identity(self):
        x = generate('high_vol_low_corr', 25, 11)
        run = run_portfolio(x, [.5, .5], 1, SyntheticCosts(2, 2, 3, 100, 100, .01))
        before = 1.
        for t, after in enumerate(run['wealth']):
            w = run['executed_weights_including_cash'][t]
            expected = (before - run['fees'][t]) * (sum(float(w[i] * x[t, i]) for i in range(2)) + w[-1])
            self.assertAlmostEqual(expected, after, places=11)
            before = after

    def test_invalid_relatives_rejected(self):
        for x in [[], [[0., 1.]], [[float('nan'), 1.]], [[-1., 1.]]]:
            with self.assertRaises(ValueError):
                relatives(x)

    def test_zero_cost_not_allowed_as_costed_evidence(self):
        with self.assertRaises(ValueError):
            SyntheticCosts(0, 1, 1, 1, 1, .1).validate()

    def test_drawdown_includes_initial_capital_and_ruin_unknown(self):
        r = run_portfolio([[.5, .5], [1., 1.]], [.5, .5])
        m = metrics(r)
        self.assertEqual(m['max_drawdown'], -.5)
        self.assertIsNone(m['risk_of_ruin_probability'])
        self.assertEqual(m['drawdown_duration_periods'], 2)

    def test_crp_decomposition_exact(self):
        d = decomposition(generate('high_vol_high_corr', 30, 7), np.array([.5, .5]))
        self.assertAlmostEqual(d['crp_log_growth'], d['weighted_asset_log_growth'] + d['exact_diversification_log_growth'])
