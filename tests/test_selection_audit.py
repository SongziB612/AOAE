import unittest
import numpy as np
from aoae.selection_audit import comparable_matrix, cscv_pbo, deflated_sharpe


class SelectionAuditTests(unittest.TestCase):
    def test_dsr_zero_mean_single_trial_half(self):
        self.assertAlmostEqual(deflated_sharpe([-.02, .02, -.01, .01], 1, .01)['dsr_iid_sensitivity'], .5)

    def test_dsr_more_search_lowers_probability(self):
        r = np.random.default_rng(13).normal(.001, .01, 252)
        values = [deflated_sharpe(r, n, .01)['dsr_iid_sensitivity'] for n in (1, 6, 20, 1000)]
        self.assertTrue(all(a > b for a, b in zip(values, values[1:])))

    def test_dsr_scale_invariance(self):
        r = np.random.default_rng(2).normal(.001, .01, 252)
        self.assertAlmostEqual(deflated_sharpe(r, 6, .01)['dsr_iid_sensitivity'], deflated_sharpe(r * 10, 6, .01)['dsr_iid_sensitivity'])

    def test_reject_invalid(self):
        for x in ([1, 1, 1, 1], [1, 2, 3, float('nan')]):
            with self.assertRaises(ValueError):
                deflated_sharpe(x, 6, .01)
        with self.assertRaises(ValueError):
            cscv_pbo(np.ones((17, 2)), 4)

    def test_pbo_identical_candidates_are_neutral(self):
        r = np.tile([-.01, .02], 8)
        self.assertEqual(cscv_pbo(np.column_stack([r, r]), 4)['subset_pbo'], .5)

    def test_balanced_preserves_all_rows_and_labels_extension(self):
        x = np.random.default_rng(52).normal(size=(243, 3))
        result = cscv_pbo(x, 8, balanced=True)
        self.assertEqual(sum(result['block_sizes']), 243)
        self.assertEqual(max(result['block_sizes']) - min(result['block_sizes']), 1)
        self.assertEqual(result['splits'], 70)
        self.assertEqual(result['method'], 'BALANCED_BLOCK_CSCV_EXTENSION')
        with self.assertRaises(ValueError):
            cscv_pbo(x, 8)

    def test_pbo_consistent_winner(self):
        r = np.tile([-.01, .01], 8)
        self.assertEqual(cscv_pbo(np.column_stack([r + .01, r]), 4)['subset_pbo'], 0)

    def test_pbo_independent_two_candidate_enumeration(self):
        x = np.random.default_rng(72).normal(size=(40, 2))
        observed = cscv_pbo(x, 4)['subset_pbo']
        losses = []
        # Independent explicit six-partition comparison; no ranking helper.
        for inside, outside in [([0,1],[2,3]),([0,2],[1,3]),([0,3],[1,2]),
                                ([1,2],[0,3]),([1,3],[0,2]),([2,3],[0,1])]:
            train = np.vstack([x[i*10:(i+1)*10] for i in inside])
            test = np.vstack([x[i*10:(i+1)*10] for i in outside])
            best = int(np.argmax(train.mean(axis=0) / train.std(axis=0, ddof=1)))
            score = test.mean(axis=0) / test.std(axis=0, ddof=1)
            losses.append(score[best] < score[1-best])
        self.assertAlmostEqual(observed, float(np.mean(losses)))
        self.assertEqual(observed, cscv_pbo(x[:, ::-1], 4)['subset_pbo'])

    def test_matrix_initial_and_exit_cost(self):
        rows = [{'arm': a, 'dates': ['2025-01-02', '2025-01-03'], 'equity_cny': [99, 110],
                 'net_pnl_after_exit_haircut_cny': 8} for a in ['a', 'b']]
        _, matrix = comparable_matrix(rows, ['a', 'b'], 100)
        self.assertAlmostEqual(float(np.prod(1 + matrix[:, 0])), 1.08)
        self.assertAlmostEqual(matrix[0, 0], -.01)
        rows[1]['dates'] = ['2025-01-02', '2025-01-04']
        with self.assertRaises(ValueError):
            comparable_matrix(rows, ['a', 'b'], 100)
