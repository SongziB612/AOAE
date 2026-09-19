from decimal import Decimal
import unittest

from aoae.shadow_accounting import advance_day, new_account


class ShadowAccountingTests(unittest.TestCase):
    def step(self, account, day='2026-09-09', prevday='2026-09-08', price=10, prevprice=10, **kwargs):
        return advance_day(account, day, prevday, {'A': price}, {'A': price}, {'A': prevprice}, **kwargs)

    def test_buy_fee_and_cash_independently(self):
        original = new_account(10000, 1000)
        state, trades = self.step(original, targets={'A': '.5'})
        self.assertEqual(state['positions']['A'], 500)
        self.assertEqual(Decimal(state['cash']), Decimal(4970))
        self.assertEqual(Decimal(state['equity']), Decimal(9970))
        self.assertEqual(original['positions'], {})
        self.assertEqual(trades[0]['kind'], 'MODELED_FILL_NOT_OBSERVED')

    def test_dividend_receivable_not_spendable_until_payment(self):
        state, _ = self.step(new_account(10000, 1000), targets={'A': '.5'})
        action = {'id': 'div', 'symbol': 'A', 'date': '2026-09-10', 'ratio': 1,
                  'cash_per_old_share': 1, 'payment_date': '2026-09-14', 'rounding': 'floor'}
        state, _ = self.step(state, '2026-09-10', '2026-09-09', price=9, actions=[action])
        self.assertEqual(Decimal(state['cash']), Decimal(4970))
        self.assertEqual(Decimal(state['equity']), Decimal(9970))
        self.assertEqual(Decimal(state['receivables'][0]['amount']), Decimal(500))
        state, _ = self.step(state, '2026-09-14', '2026-09-10', price=9, prevprice=9)
        self.assertEqual(Decimal(state['cash']), Decimal(5470))
        self.assertEqual(state['receivables'], [])

    def test_split_preserves_value(self):
        state, _ = self.step(new_account(10000, 1000), targets={'A': '.5'})
        action = {'id': 'split', 'symbol': 'A', 'date': '2026-09-10', 'ratio': 2,
                  'cash_per_old_share': 0, 'payment_date': None, 'rounding': 'floor'}
        state, _ = self.step(state, '2026-09-10', '2026-09-09', price=5, actions=[action])
        self.assertEqual(state['positions']['A'], 1000)
        self.assertEqual(Decimal(state['equity']), Decimal(9970))

    def test_buy_on_exdate_does_not_earn_old_entitlement(self):
        action = {'id': 'div', 'symbol': 'A', 'date': '2026-09-09', 'ratio': 1,
                  'cash_per_old_share': 1, 'payment_date': '2026-09-10', 'rounding': 'floor'}
        state, _ = self.step(new_account(10000, 1000), price=9, actions=[action], targets={'A': '.5'})
        self.assertEqual(state['receivables'], [])

    def test_pause_exits_next_session_not_at_guaranteed_price(self):
        state, _ = self.step(new_account(10000, 1000), targets={'A': '.5'})
        state, _ = self.step(state, '2026-09-10', '2026-09-09', price=7)
        self.assertTrue(state['paused'])
        state, trades = self.step(state, '2026-09-11', '2026-09-10', price=6, prevprice=7, targets={'A': 1})
        self.assertEqual(state['positions']['A'], 0)
        self.assertEqual(trades[0]['side'], 'SELL')
        self.assertLess(Decimal(state['equity']), Decimal(9000))

    def test_partial_fill_and_gap_affordability(self):
        state, _ = self.step(new_account(10000, 1000), price=20, targets={'A': 1}, fill_fraction='.5')
        self.assertEqual(state['positions']['A'], 400)
        self.assertGreaterEqual(Decimal(state['cash']), 0)

    def test_invalid_input_rejected(self):
        with self.assertRaises(ValueError):
            self.step(new_account(), price=float('nan'))
        with self.assertRaises(ValueError):
            self.step(new_account(), targets={'A': 2})

    def test_float_weight_epsilon_is_not_economic_leverage(self):
        state, _ = self.step(new_account(10000, 1000), targets={'A': 1.0000000000000002})
        self.assertGreaterEqual(Decimal(state['cash']), 0)
        with self.assertRaises(ValueError):
            self.step(new_account(), targets={'A': 1.000001})
