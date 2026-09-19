from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import unittest

from aoae.manual_ticket import prepare, reconcile


NOW = '2026-10-08T09:31:05+08:00'


def fixture():
    return json.loads((Path(__file__).resolve().parents[1] / 'research/manual_execution/engineering-example.json').read_text())


def fill(ticket, **changes):
    return dict(ticket_id=ticket['ticket_id'], fill_id='f1', execution_at='2026-10-08T09:31:10+08:00',
                symbol='510300', side='BUY', quantity='1200', price='4.000', commission_cny='14.4', other_fees_cny='0') | changes


class ManualTicketTests(unittest.TestCase):
    def test_no_signal_never_invents_order(self):
        t = prepare({'signal': None}, NOW)
        self.assertEqual(t['status'], 'WAIT_NO_SIGNAL')
        self.assertEqual(t['legs'], [])

    def test_current_quote_sizing_and_no_mutation(self):
        r = fixture()
        original = deepcopy(r)
        t = prepare(r, NOW)
        self.assertEqual(t['legs'][0]['quantity'], 1200)
        self.assertEqual(t['legs'][0]['limit_price'], '4.000')
        self.assertFalse(t['capital_authorized'])
        self.assertEqual(r, original)
        self.assertEqual(t['seconds_after_model_open'], 65)

    def test_stale_future_and_crossed_quotes_rejected(self):
        for change in ({'as_of': '2026-10-08T09:29:00+08:00'},
                       {'as_of': '2026-10-08T09:32:00+08:00'}, {'bid': '4.1'}, {'ask': 'NaN'}, {'tradable': False}):
            r = fixture()
            r['quotes']['510300'].update(change)
            with self.assertRaises(ValueError):
                prepare(r, NOW)

    def test_stale_account_and_outstanding_orders(self):
        for change in ({'as_of': '2026-10-08T09:29:00+08:00'}, {'open_orders': ['pending']}):
            r = fixture()
            r['account'].update(change)
            with self.assertRaises(ValueError):
                prepare(r, NOW)

    def test_expired_and_unreviewed_signals(self):
        with self.assertRaises(ValueError):
            prepare(fixture(), '2026-10-08T10:00:00+08:00')
        r = fixture()
        r['signal']['review_status'] = 'DRAFT'
        with self.assertRaises(ValueError):
            prepare(r, NOW)

    def test_fees_cannot_overdraw_cash(self):
        r = fixture()
        r['signal']['weights']['model']['510300'] = 1
        t = prepare(r, NOW)
        self.assertEqual(t['status'], 'BLOCKED')
        self.assertEqual(t['legs'], [])

    def test_unavailable_sale_blocked(self):
        r = fixture()
        r['account']['positions'] = {'510300': 1000}
        r['signal']['weights']['model']['510300'] = 0
        self.assertEqual(prepare(r, NOW)['status'], 'BLOCKED')

    def test_independent_cash_arithmetic(self):
        t = prepare(fixture(), NOW)
        result = reconcile(t, [fill(t)], '2026-10-08T09:31:20+08:00')
        self.assertEqual(result['status'], 'COMPLETE_REPORTED')
        self.assertEqual(Decimal(result['reported_cash_cny']), Decimal('10000') - 1200 * Decimal('4') - Decimal('14.4'))
        self.assertEqual(result['reported_positions'], {'510300': 1200})

    def test_partial_exchange_fills_need_not_be_full_lots(self):
        t = prepare(fixture(), NOW)
        result = reconcile(t, [fill(t, quantity='37')], '2026-10-08T09:31:20+08:00')
        self.assertEqual(result['status'], 'PARTIAL_REPORTED')
        self.assertEqual(result['unfilled']['510300:BUY'], 1163)
        self.assertFalse(result['automatic_follow_up_allowed'])

    def test_duplicate_overfill_nonfinite_wrong_side_and_limit(self):
        t = prepare(fixture(), NOW)
        bad = [dict(quantity='1201'), dict(quantity='1.5'), dict(price='NaN'),
               dict(price='4.001'), dict(side='SELL'), dict(commission_cny='-5'), dict(ticket_id='wrong')]
        for change in bad:
            self.assertEqual(reconcile(t, [fill(t, **change)], '2026-10-08T09:31:20+08:00')['status'], 'VIOLATION')
        self.assertEqual(reconcile(t, [fill(t), fill(t)], '2026-10-08T09:31:20+08:00')['status'], 'VIOLATION')

    def test_late_fill_is_accounted_but_ledger_invalid(self):
        t = prepare(fixture(), NOW)
        r = reconcile(t, [fill(t, execution_at='2026-10-08T09:32:10+08:00')], '2026-10-08T09:33:00+08:00')
        self.assertEqual(r['status'], 'VIOLATION')
        self.assertFalse(r['ledger_valid'])
        self.assertEqual(r['reported_positions']['510300'], 1200)

    def test_changed_ticket_rejected(self):
        t = prepare(fixture(), NOW)
        t['legs'][0]['quantity'] = 2000
        with self.assertRaises(ValueError):
            reconcile(t, [], NOW)

    def test_other_fees_are_deducted(self):
        t = prepare(fixture(), NOW)
        r = reconcile(t, [fill(t, other_fees_cny='1.25')], '2026-10-08T09:31:20+08:00')
        self.assertEqual(Decimal(r['reported_cash_cny']), Decimal('5184.35'))
        self.assertEqual(Decimal(r['reported_total_fees_cny']), Decimal('15.65'))


if __name__ == '__main__':
    unittest.main()
