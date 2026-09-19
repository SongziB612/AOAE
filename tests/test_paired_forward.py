import unittest
from aoae.paired_forward import freshness, initial_accounts, admit_signal, apply_simulated_fill


class PairedForwardTests(unittest.TestCase):
    def setUp(self):
        self.freeze = {'frozen_at_utc': '2026-09-05T00:00:00+00:00', 'arms': ['model', 'equal', 'matched'], 'initial_paper_capital_per_arm_cny': 300000}
        self.signal = {'signal_close_at': '2026-09-30T07:00:00+00:00', 'execution_not_before': '2026-10-08T01:30:00+00:00', 'execution_expires_at': '2026-10-08T02:00:00+00:00',
            'review_status': 'VERIFIED_CALENDAR_ACTIONS_AND_DATA', 'review_evidence_sha256': 'a' * 64, 'input_sha256': 'b' * 64,
            'weights': {s: {'510300': .5} for s in self.freeze['arms']}}
        # Dates are a timing fixture, not a certified holiday calendar.

    def test_stale_is_not_new_market_day(self):
        self.assertEqual(freshness({'A': {'last_market_date': '2026-09-07'}}, '2026-09-08'), 'BLOCKED_STALE_MARKET_DATA')

    def test_late_signal_and_unreviewed_signal_rejected(self):
        with self.assertRaises(ValueError):
            admit_signal(self.signal, self.freeze, '2026-10-08T02:00:00+00:00')
        self.signal['review_status'] = 'UNKNOWN'
        with self.assertRaises(ValueError):
            admit_signal(self.signal, self.freeze, '2026-09-30T08:00:00+00:00')

    def test_invalid_expiry_and_digest_rejected(self):
        self.signal['execution_expires_at'] = self.signal['execution_not_before']
        with self.assertRaises(ValueError):
            admit_signal(self.signal, self.freeze, '2026-09-30T08:00:00+00:00')
        self.signal['execution_expires_at'] = '2026-10-08T02:00:00+00:00'
        self.signal['input_sha256'] = 'unverified'
        with self.assertRaises(ValueError):
            admit_signal(self.signal, self.freeze, '2026-09-30T08:00:00+00:00')

    def test_isolated_ledger_and_duplicate_rejection(self):
        signal = admit_signal(self.signal, self.freeze, '2026-09-30T08:00:00+00:00')
        original = initial_accounts(self.freeze)
        fill = {'kind': 'SIMULATED_FILL', 'signal_id': signal['signal_id'], 'fill_id': 'test-1', 'execution_at': '2026-10-08T01:31:00+00:00', 'arm': 'model', 'symbol': '510300', 'side': 'BUY', 'quantity': 100, 'price': 4., 'cost_cny': 5.}
        result = apply_simulated_fill(original, signal, fill, '2026-10-08T02:00:00+00:00')
        self.assertEqual(result['model']['cash_cny'], 299595.)
        self.assertEqual(result['equal']['cash_cny'], 300000.)
        self.assertEqual(original['model']['cash_cny'], 300000.)
        with self.assertRaises(ValueError):
            apply_simulated_fill(result, signal, fill, '2026-10-08T02:00:00+00:00')
        fill['quantity'] = 1000000
        with self.assertRaises(ValueError):
            apply_simulated_fill(original, signal, fill, '2026-10-08T02:00:00+00:00')
