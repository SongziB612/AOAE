import unittest

import pandas as pd

from aoae.corporate_action_replay import Action, infer_actions, replay, total_return_signals


class CorporateActionTests(unittest.TestCase):
    def test_zero_fill_cannot_create_profit(self):
        dates = pd.date_range('2024-01-01', periods=3)
        prices = pd.DataFrame({'A': [10., 10., 20.]}, index=dates)
        schedule = {dates[1]: ({'A': 1.}, {}, str(dates[0].date()), {})}
        eq, orders, _ = replay(prices, prices, schedule, [], ['A'], str(dates[1].date()), str(dates[-1].date()), initial=2005., buy_fill_fraction=0.)
        self.assertEqual(orders, [])
        self.assertEqual(eq.tolist(), [2005., 2005.])

    def test_half_fill_rounds_to_whole_lots(self):
        dates = pd.date_range('2024-01-01', periods=2)
        prices = pd.DataFrame({'A': [10., 10.]}, index=dates)
        schedule = {dates[1]: ({'A': 1.}, {}, str(dates[0].date()), {})}
        _, orders, _ = replay(prices, prices, schedule, [], ['A'], str(dates[1].date()), str(dates[-1].date()), initial=3005., commission=0., slippage_bps=0., buy_fill_fraction=.5)
        self.assertEqual(orders[0]['quantity'], 100)

    def test_split_preserves_signal_value(self):
        prices = pd.DataFrame({'A': [10., 5., 5.5]}, index=pd.date_range('2024-01-01', periods=3))
        action = Action('A', prices.index[1], 2., 0.)
        result = total_return_signals(prices, [action])
        self.assertEqual(result.A.tolist(), [1., 1., 1.1])

    def test_dividend_preserves_signal_value(self):
        prices = pd.DataFrame({'A': [10., 9., 9.]}, index=pd.date_range('2024-01-01', periods=3))
        result = total_return_signals(prices, [Action('A', prices.index[1], 1., 1.)])
        self.assertEqual(result.A.tolist(), [1., 1., 1.])

    def test_future_action_does_not_change_past_index(self):
        prices = pd.DataFrame({'A': [10., 11., 5.5]}, index=pd.date_range('2024-01-01', periods=3))
        full = total_return_signals(prices, [Action('A', prices.index[2], 2., 0.)])
        short = total_return_signals(prices.iloc[:2], [])
        pd.testing.assert_frame_equal(full.iloc[:2], short)

    def test_rejects_ambiguous_factors(self):
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            infer_actions('A', [{'d': '1900-01-01', 's': 1, 'u': 0, 'f': 1}, {'d': '2024-01-01', 's': 2, 'u': 1, 'f': 1}])

    def test_receivable_is_not_immediately_spendable_cash(self):
        dates = pd.date_range('2024-01-01', periods=4)
        prices = pd.DataFrame({'A': [10., 10., 9., 9.]}, index=dates)
        schedule = {dates[1]: ({'A': 1.}, {}, str(dates[0].date()), {})}
        action = Action('A', dates[2], 1., 1.)
        eq, orders, state = replay(prices, prices, schedule, [action], ['A'], str(dates[1].date()), str(dates[-1].date()), initial=2005., commission=0., slippage_bps=0., pay_lag_sessions=5)
        self.assertEqual(orders[0]['quantity'], 200)
        self.assertEqual(state['ending_receivables_cny'], 200.)
        self.assertEqual(state['ending_cash_cny'], 0.)
        self.assertEqual(eq.tolist(), [2000., 2000., 2000.])

    def test_gap_after_pause_can_exceed_loss_limit(self):
        dates = pd.date_range('2024-01-01', periods=4)
        prices = pd.DataFrame({'A': [10., 10., 8., 5.]}, index=dates)
        schedule = {dates[1]: ({'A': 1.}, {}, str(dates[0].date()), {})}
        eq, orders, state = replay(prices, prices, schedule, [], ['A'], str(dates[1].date()), str(dates[-1].date()), initial=2005., commission=0., slippage_bps=0., pause_loss=300.)
        self.assertTrue(state['paused'])
        self.assertEqual(orders[-1]['side'], 'SELL')
        self.assertLess(eq.iloc[-1], 2005. - 300.)

    def test_actual_payment_date_releases_receivable(self):
        dates = pd.date_range('2024-01-01', periods=4)
        prices = pd.DataFrame({'A': [10., 10., 9., 9.]}, index=dates)
        schedule = {dates[1]: ({'A': 1.}, {}, str(dates[0].date()), {})}
        action = Action('A', dates[2], 1., 1., dates[3])
        _, _, state = replay(prices, prices, schedule, [action], ['A'], str(dates[1].date()), str(dates[-1].date()), initial=2005., commission=0., slippage_bps=0., use_payment_dates=True)
        self.assertEqual(state['ending_receivables_cny'], 0.)
        self.assertEqual(state['ending_cash_cny'], 200.)

    def test_split_changes_units_without_creating_wealth(self):
        dates = pd.date_range('2024-01-01', periods=3)
        prices = pd.DataFrame({'A': [10., 10., 5.]}, index=dates)
        schedule = {dates[1]: ({'A': 1.}, {}, str(dates[0].date()), {})}
        eq, _, state = replay(prices, prices, schedule, [Action('A', dates[2], 2., 0.)], ['A'], str(dates[1].date()), str(dates[-1].date()), initial=2005., commission=0., slippage_bps=0.)
        self.assertEqual(state['ending_positions']['A'], 400)
        self.assertEqual(eq.tolist(), [2000., 2000.])

    def test_lower_open_does_not_expand_prior_close_draft(self):
        dates = pd.date_range('2024-01-01', periods=2)
        closes = pd.DataFrame({'A': [10., 5.]}, index=dates)
        schedule = {dates[1]: ({'A': 1.}, {}, str(dates[0].date()), {})}
        _, orders, _ = replay(closes, closes, schedule, [], ['A'], str(dates[1].date()), str(dates[1].date()), initial=2005., commission=0., slippage_bps=0.)
        self.assertEqual(orders[0]['quantity'], 200)

    def test_issuer_round_up_rule_preserved(self):
        dates = pd.date_range('2024-01-01', periods=3)
        prices = pd.DataFrame({'A': [10., 10., 10. / 1.14539]}, index=dates)
        schedule = {dates[1]: ({'A': 1.}, {}, str(dates[0].date()), {})}
        action = Action('A', dates[2], 1.14539, 0., rounding='ceil')
        _, _, state = replay(prices, prices, schedule, [action], ['A'], str(dates[1].date()), str(dates[-1].date()), initial=2005., commission=0., slippage_bps=0.)
        self.assertEqual(state['ending_positions']['A'], 230)
