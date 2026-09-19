import json
from pathlib import Path
import unittest
from uuid import uuid4

from aoae.forward_journal import ForwardJournal


class ForwardJournalTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(__file__).resolve().parents[1] / 'data/runtime' / ('test-journal-' + uuid4().hex + '.sqlite3')
        self.addCleanup(lambda: self.path.unlink(missing_ok=True))
        self.journal = ForwardJournal(self.path)
        self.init = {'kind': 'INIT', 'freeze_sha256': 'f' * 64,
                     'freeze': {'initial_paper_capital_per_arm_cny': 300000, 'arms': ['model', 'equal', 'matched']}}
        self.journal.append('genesis', self.init)

    def event(self, day='2026-09-08'):
        return {'kind': 'CASH_CHECKPOINT', 'evidence': {'freeze_sha256': 'f' * 64,
                'freshness_status': 'CURRENT', 'expected_market_date': day, 'actual_market_dates': [day]}}

    def test_restart_and_idempotence(self):
        self.journal.append('day', self.event())
        self.assertFalse(self.journal.append('day', self.event()))
        audit = ForwardJournal(self.path).audit()
        self.assertEqual(audit['events'], 2)
        self.assertEqual(audit['state']['checkpoints'], 1)
        self.assertEqual(audit['state']['simulated_fills'], 0)
        self.assertEqual([v['cash_cny'] for v in audit['state']['accounts'].values()], [300000] * 3)

    def test_reject_changed_duplicate(self):
        self.journal.append('day', self.event())
        with self.assertRaises(ValueError):
            self.journal.append('day', self.event('2026-09-09'))
        self.assertEqual(self.journal.audit()['events'], 2)

    def test_reject_backwards_or_stale_and_rollback(self):
        self.journal.append('day', self.event())
        with self.assertRaises(ValueError):
            self.journal.append('earlier', self.event('2026-09-07'))
        bad = self.event('2026-09-09')
        bad['evidence']['freshness_status'] = 'BLOCKED_STALE_MARKET_DATA'
        with self.assertRaises(ValueError):
            self.journal.append('stale', bad)
        self.assertEqual(self.journal.audit()['events'], 2)

    def test_tampering_detected(self):
        with self.journal.connect() as db:
            db.execute('UPDATE events SET payload = ?', (json.dumps({'kind': 'BAD'}),))
        with self.assertRaises(ValueError):
            self.journal.audit()

    def test_no_order_event_supported(self):
        with self.assertRaises(ValueError):
            self.journal.append('order', {'kind': 'LIVE_ORDER'})
        self.assertEqual(self.journal.audit()['events'], 1)
