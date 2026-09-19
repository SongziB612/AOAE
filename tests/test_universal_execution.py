import copy
import unittest

import numpy as np
import pandas as pd

from aoae.universal import two_asset_grid
from aoae.universal_execution import CashAction, gross_up_next_open_targets, replay_next_open


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.dates = pd.bdate_range('2024-01-02', periods=5)
        self.prices = pd.DataFrame({'A': [10.] * 5, 'B': [20.] * 5}, index=self.dates)
        self.cap = self.prices * 100
        self.targets = {str(self.dates[1].date()): {'A': 1., 'B': 0.}}

    def run_account(self, **kw):
        return replay_next_open(self.prices, self.prices, self.cap, self.targets, **kw)

    def test_next_open_whole_shares_positive_costs(self):
        result = self.run_account()
        self.assertEqual(result['rows'][0]['equity'], 10000.)
        self.assertLess(result['rows'][1]['equity'], 10000.)
        self.assertTrue(all(o['signal_date'] < o['date'] and type(o['quantity']) is int and o['fee'] > 0 for o in result['orders']))

    def test_no_fill_no_invented_profit(self):
        self.cap *= 0
        result = self.run_account()
        self.assertEqual(result['orders'], [])
        self.assertEqual(result['rows'][-1]['equity'], 10000.)

    def test_dividend_not_cash_before_payment(self):
        day = str(self.dates[2].date())
        action = CashAction('A', day, str(self.dates[0].date()), str(self.dates[4].date()), 1.)
        result = self.run_account(actions=[action])
        q = result['rows'][1]['positions']['A']
        self.assertEqual(result['rows'][2]['receivable'], q)
        self.assertEqual(result['rows'][2]['cash'], result['rows'][1]['cash'])
        self.assertAlmostEqual(result['rows'][4]['cash'], result['rows'][1]['cash'] + q)

    def test_unsettled_sale_cannot_fund_replacement(self):
        self.targets[str(self.dates[2].date())] = {'A': 0., 'B': 1.}
        result = self.run_account()
        row = result['rows'][2]
        self.assertGreater(row['receivable'], 9000)
        self.assertEqual(row['positions']['B'], 0)

    def test_gap_and_capacity_can_exceed_loss_budget(self):
        self.prices.loc[self.dates[2]:, 'A'] = [8., 5., 5.]
        self.cap.loc[self.dates[3]:, 'A'] = 0
        result = self.run_account()
        self.assertTrue(result['rows'][-1]['paused'])
        self.assertLess(result['rows'][-1]['equity'], 9000)
        self.assertGreater(result['rows'][-1]['positions']['A'], 0)

    def test_current_future_close_cannot_change_current_target(self):
        grid = two_asset_grid(11)
        before = gross_up_next_open_targets(self.prices, grid)
        self.prices.iloc[2:, 0] *= 2
        after = gross_up_next_open_targets(self.prices, grid)
        self.assertEqual(before[str(self.dates[2].date())], after[str(self.dates[2].date())])

    def test_reject_same_close_target(self):
        self.targets[str(self.dates[0].date())] = {'A': 1.}
        with self.assertRaises(ValueError):
            self.run_account()

    def test_reject_late_dividend_information(self):
        day = str(self.dates[2].date())
        with self.assertRaises(ValueError):
            self.run_account(actions=[CashAction('A', day, day, day, 1.)])

    def test_bad_inputs_fail(self):
        for kw in ({'commission_bps': 0}, {'settlement_sessions': -1}, {'pause_loss': 10000}):
            with self.assertRaises(ValueError):
                self.run_account(**kw)
        self.prices.iloc[2, 0] = np.nan
        with self.assertRaises(ValueError):
            self.run_account()

    def test_independent_decimal_audit_and_tampering(self):
        from scripts.run_up_execution_checks import experiment
        from scripts.audit_universal_execution import audit
        result = experiment()
        self.assertEqual(result['independent_audit']['status'], 'PASS')
        for mutation in ('fee', 'cash', 'signal', 'capacity'):
            record = copy.deepcopy(result['fixture'])
            if mutation == 'fee':
                record['result']['orders'][0]['fee'] += 1
            elif mutation == 'cash':
                record['result']['rows'][3]['cash'] += 100
            elif mutation == 'signal':
                record['result']['orders'][0]['signal_date'] = record['dates'][1]
            else:
                record['opening_capacity'][1]['A'] = 0
            with self.assertRaises(ValueError):
                audit(record)
