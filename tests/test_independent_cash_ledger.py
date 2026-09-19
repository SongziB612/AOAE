import unittest

from aoae.independent_cash_ledger import verify_ledger


class IndependentLedgerTests(unittest.TestCase):
    def test_dividend_after_sale_remains_receivable(self):
        dates = ['2024-01-01', '2024-01-02', '2024-01-03']
        closes = {d: {'A': p} for d, p in zip(dates, [10, 9, 9])}
        orders = [{'date': dates[0], 'symbol': 'A', 'quantity': 100, 'price': 10, 'side': 'BUY', 'cost': 5},
                  {'date': dates[1], 'symbol': 'A', 'quantity': 100, 'price': 9, 'side': 'SELL', 'cost': 5}]
        actions = [{'date': dates[1], 'symbol': 'A', 'ratio': 1, 'cash_per_old_share': 1, 'payment_date': dates[2], 'rounding': 'floor'}]
        self.assertEqual(verify_ledger(dates, closes, orders, actions, 1005, 0, 0), [1000, 995, 995])

    def test_tampered_fee_rejected(self):
        with self.assertRaisesRegex(ValueError, 'fee disagrees'):
            verify_ledger(['2024-01-01'], {'2024-01-01': {'A': 10}}, [{'date': '2024-01-01', 'symbol': 'A', 'quantity': 100, 'price': 10, 'side': 'BUY', 'cost': 0}], [], 1005, 0, 0)

    def test_unfunded_buy_rejected(self):
        with self.assertRaisesRegex(ValueError, 'unfunded'):
            verify_ledger(['2024-01-01'], {'2024-01-01': {'A': 10}}, [{'date': '2024-01-01', 'symbol': 'A', 'quantity': 100, 'price': 10, 'side': 'BUY', 'cost': 5}], [], 1000, 0, 0)
