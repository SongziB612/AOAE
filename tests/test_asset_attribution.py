import unittest
from aoae.asset_attribution import attribute


class AttributionTests(unittest.TestCase):
    def test_dividend_ex_not_payment_profit(self):
        dates = ['2024-01-02', '2024-01-03', '2024-01-04']
        marks = {d: {'A': 10. if i == 0 else 9.} for i, d in enumerate(dates)}
        orders = [{'date': dates[0], 'symbol': 'A', 'side': 'BUY', 'quantity': 100, 'price': 10., 'cost': 8.}]
        actions = [{'date': dates[1], 'symbol': 'A', 'ratio': 1., 'cash_per_old_share': 1., 'payment_date': dates[2], 'rounding': 'floor'}]
        result = attribute(dates, marks, orders, actions, 2000, .003, 30)
        self.assertEqual([r['reconstructed_equity_cny'] for r in result['daily']], [1992., 1992., 1992.])
        self.assertEqual(result['assets']['A']['dividend_entitlement_cny'], 100.)

    def test_split_rounding_not_double_counted(self):
        dates = ['2024-01-02', '2024-01-03']
        marks = {dates[0]: {'A': 10.}, dates[1]: {'A': 5.}}
        orders = [{'date': dates[0], 'symbol': 'A', 'side': 'BUY', 'quantity': 100, 'price': 10., 'cost': 8.}]
        actions = [{'date': dates[1], 'symbol': 'A', 'ratio': 2.001, 'cash_per_old_share': 0., 'payment_date': None, 'rounding': 'ceil'}]
        result = attribute(dates, marks, orders, actions, 2000, .003, 30)
        self.assertEqual(result['assets']['A']['ending_quantity'], 201)
        self.assertEqual(result['assets']['A']['gross_cashflow_pnl_cny'], 5.)
        self.assertEqual(result['assets']['A']['split_rounding_mark_cny'], 4.5)

    def test_fee_tampering_and_uncovered_sale_fail(self):
        for side, cost in [('BUY', 0), ('SELL', 8)]:
            with self.assertRaises(ValueError):
                attribute(['2024-01-02'], {'2024-01-02': {'A': 10}},
                    [{'date': '2024-01-02', 'symbol': 'A', 'side': side, 'quantity': 100, 'price': 10, 'cost': cost}], [], 2000, .003, 30)
