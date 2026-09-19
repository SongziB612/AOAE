from copy import deepcopy
from pathlib import Path
from uuid import uuid4
import unittest
from unittest.mock import patch
import json
from hashlib import sha256

from aoae.forward_journal import ForwardJournal, digest
from aoae.manual_bridge import read_shadow, prepare_from_journal
from aoae.paired_forward import admit_signal
from aoae.shadow_cycle import reduce_shadow


class ManualBridgeTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.path = self.root / 'data/runtime' / ('manual-bridge-test-' + uuid4().hex + '.sqlite3')
        self.addCleanup(lambda: self.path.unlink(missing_ok=True))

    def fixture(self):
        return {'arms': ['causal_total_return_momentum_overlay'], 'initial_paper_capital_per_arm_cny': 300000,
                'risk_pause_loss_cny': 100000, 'capital_authorized': False,
                'orders_authorized': False, 'broker_connection_authorized': False}

    def test_read_only_matches_original_audit(self):
        path = self.path
        journal = ForwardJournal(path, reducer=reduce_shadow)
        journal.append('init', {'kind': 'SHADOW_INIT', 'freeze': self.fixture()})
        original = journal.audit()
        before = path.read_bytes()
        actual = read_shadow(path)
        self.assertEqual(actual['state'], original['state'])
        self.assertEqual(actual['head'], original['head_sha256'])
        self.assertEqual(before, path.read_bytes())
        ticket = prepare_from_journal(self.root, actual, self.fixture(), {}, None, '2026-09-13T10:00:00+00:00')
        self.assertEqual(ticket['status'], 'WAIT_NO_SIGNAL')
        self.assertEqual(ticket['legs'], [])

    def test_missing_journal_is_not_created(self):
        with self.assertRaises(FileNotFoundError):
            read_shadow(self.path)
        self.assertFalse(self.path.exists())

    def test_paper_cash_never_substitutes_for_account(self):
        audit = {'head': 'a'*64, 'events': 1, 'state': {'freeze': self.fixture(), 'pending_signal': {'unread': True}}}
        with self.assertRaisesRegex(ValueError, 'paper balances'):
            prepare_from_journal(Path.cwd(), audit, self.fixture(), {}, None, '2026-09-13T10:00:00+00:00')

    def test_mismatched_freeze_rejected(self):
        audit = {'state': {'freeze': self.fixture()}}
        freeze = deepcopy(self.fixture())
        freeze['risk_pause_loss_cny'] = 50000
        with self.assertRaises(ValueError):
            prepare_from_journal(Path.cwd(), audit, freeze, {}, None, '2026-09-13T10:00:00+00:00')

    def pending_fixture(self):
        request = json.loads((self.root/'research/manual_execution/engineering-example.json').read_text())
        freeze = self.fixture() | {'frozen_at_utc': '2026-09-05T00:00:00+00:00'}
        source = 'research/manual_execution/engineering-example.json'
        review = {'source_sha256': {source: sha256((self.root/source).read_bytes()).hexdigest()}}
        signal = request['signal']
        signal['weights'] = {'causal_total_return_momentum_overlay': signal['weights']['model']}
        signal['review_evidence_sha256'] = digest(review)
        admitted = admit_signal(signal, freeze, request['captured_at'])
        audit = {'head': 'a'*64, 'events': 2, 'reviews': [review],
                 'state': {'freeze': freeze, 'pending_signal': admitted}}
        fees = {'confirmation_status': 'USER_CONFIRMED_EFFECTIVE_NOT_BROKER_API_VERIFIED',
                'fees': {'commission_rate': '.0002', 'minimum_cny': '5', 'basis': 'synthetic test'}}
        return request, freeze, audit, fees

    def test_pending_signal_uses_snapshot_and_confirmed_fee(self):
        request, freeze, audit, fees = self.pending_fixture()
        t = prepare_from_journal(self.root, audit, freeze, fees, request, '2026-10-08T09:31:05+08:00')
        self.assertEqual(t['status'], 'PAPER_REVIEW_READY')
        self.assertEqual(t['legs'][0]['quantity'], 1200)
        self.assertEqual(t['legs'][0]['estimated_commission_cny'], '5')
        self.assertEqual(t['initial_available_cash_cny'], '10000')
        self.assertFalse(t['orders_authorized'])

    def test_changed_reviewed_source_rejected(self):
        request, freeze, audit, fees = self.pending_fixture()
        with patch.object(Path, 'read_bytes', return_value=b'changed'):
            with self.assertRaisesRegex(ValueError, 'reviewed source changed'):
                prepare_from_journal(self.root, audit, freeze, fees, request, '2026-10-08T09:31:05+08:00')
