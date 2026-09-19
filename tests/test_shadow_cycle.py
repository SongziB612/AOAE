from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
import unittest

from aoae.forward_journal import ForwardJournal, digest
from aoae.shadow_cycle import reduce_shadow


class ShadowCycleTests(unittest.TestCase):
    """Synthetic clock and one-asset fixtures, never real forward evidence."""
    def setUp(self):
        self.path = Path(__file__).resolve().parents[1] / 'data/runtime' / ('shadow-test-' + uuid4().hex + '.sqlite3')
        self.addCleanup(lambda: self.path.unlink(missing_ok=True))
        self.j = ForwardJournal(self.path, reducer=reduce_shadow)
        self.freeze = {'frozen_at_utc': '2026-09-05T00:00:00+00:00', 'arms': ['model', 'equal', 'matched'],
                       'initial_paper_capital_per_arm_cny': 10000, 'risk_pause_loss_cny': 1000,
                       'capital_authorized': False, 'orders_authorized': False, 'broker_connection_authorized': False}
        self.append('init', {'kind': 'SHADOW_INIT', 'freeze': self.freeze}, '2026-09-29T08:00:00+00:00')

    def append(self, key, event, at):
        with patch('aoae.forward_journal.datetime') as clock:
            clock.now.return_value = datetime.fromisoformat(at)
            return self.j.append(key, event)

    def signal(self):
        review = {'kind': 'SIGNAL_INPUTS_AND_CALENDAR', 'status': 'REVIEWED',
                  'reviewed_at': '2026-09-30T07:30:00+00:00', 'source_sha256': {'synthetic': 'a' * 64},
                  'signal_day': '2026-09-30', 'next_session': '2026-10-08',
                  'actions_covered_through': '2026-09-30', 'prices_through': '2026-09-30', 'input_sha256': 'b' * 64}
        signal = {'signal_close_at': '2026-09-30T07:00:00+00:00', 'execution_not_before': '2026-10-08T01:30:00+00:00',
                  'execution_expires_at': '2026-10-08T02:00:00+00:00', 'review_status': 'VERIFIED_CALENDAR_ACTIONS_AND_DATA',
                  'review_evidence_sha256': digest(review), 'input_sha256': 'b' * 64,
                  'weights': {'model': {'A': .5}, 'equal': {'A': 1}, 'matched': {'A': .5}}}
        return {'kind': 'PRESAVE_SIGNAL', 'signal': signal, 'review': review, 'review_sha256': digest(review)}

    def day(self, date='2026-10-08', previous='2026-09-30'):
        inputs = {'opens': {'A': 10}, 'closes': {'A': 10}, 'previous_close': {'A': 10}, 'actions': []}
        review = {'kind': 'DAY_PRICES_AND_ACTIONS', 'status': 'REVIEWED',
                  'reviewed_at': date + 'T08:00:00+00:00', 'source_sha256': {'synthetic': 'a' * 64},
                  'day': date, 'previous_session': previous, 'input_sha256': digest(inputs)}
        return {'kind': 'MODELED_DAY', 'day': date, 'previous_day': previous, 'inputs': inputs,
                'open_at': date + 'T01:30:00+00:00', 'close_at': date + 'T07:00:00+00:00',
                'review': review, 'review_sha256': digest(review)}

    def test_signal_fill_and_restart(self):
        self.append('signal', self.signal(), '2026-09-30T08:00:00+00:00')
        self.append('day', self.day(), '2026-10-08T08:01:00+00:00')
        audit = ForwardJournal(self.path, reducer=reduce_shadow).audit()
        self.assertEqual(audit['events'], 3)
        state = audit['state']
        self.assertEqual(state['accounts']['model']['positions']['A'], 500)
        self.assertEqual(state['accounts']['equal']['positions']['A'], 900)
        self.assertEqual(state['daily'][0]['observed_broker_fills'], 0)
        self.assertEqual(state['accounts']['model']['equity'], '9970.000')

    def test_late_signal_fails_without_writing(self):
        with self.assertRaises(ValueError):
            self.append('late', self.signal(), '2026-10-08T03:00:00+00:00')
        self.assertEqual(self.j.audit()['events'], 1)

    def test_changed_price_fails_atomically(self):
        self.append('signal', self.signal(), '2026-09-30T08:00:00+00:00')
        event = self.day()
        event['inputs']['opens']['A'] = 1
        with self.assertRaises(ValueError):
            self.append('bad', event, '2026-10-08T08:01:00+00:00')
        self.assertEqual(self.j.audit()['events'], 2)
        self.assertIsNotNone(self.j.audit()['state']['pending_signal'])

    def test_missed_window_is_not_backfilled(self):
        self.append('signal', self.signal(), '2026-09-30T08:00:00+00:00')
        self.append('day', self.day('2026-10-09', '2026-10-08'), '2026-10-09T08:01:00+00:00')
        state = self.j.audit()['state']
        self.assertEqual(state['daily'][0]['signal_outcome'], 'MISSED_NOT_BACKFILLED')
        self.assertEqual(state['accounts']['model']['fills'], 0)

    def test_no_review_no_signal(self):
        event = self.signal()
        event['review']['status'] = 'UNKNOWN'
        event['review_sha256'] = digest(event['review'])
        with self.assertRaises(ValueError):
            self.append('bad', event, '2026-09-30T08:00:00+00:00')
