"""Synthetic evidence fixtures; no external PDF or market feed required."""
from hashlib import sha256
import json
from pathlib import Path
import shutil
from uuid import uuid4
import unittest

import pandas as pd

from aoae.corporate_action_guard import verify_known_action_anchors
from aoae.corporate_action_replay import Action


class CorporateActionGuardTests(unittest.TestCase):
    def setUp(self):
        workspace = Path(__file__).resolve().parents[1]
        self.root = workspace / 'data/runtime' / ('action-guard-test-' + uuid4().hex)
        self.root.mkdir()

        def cleanup():
            target = self.root.resolve()
            if target.parent != (workspace / 'data/runtime').resolve() or not target.name.startswith('action-guard-test-'):
                raise ValueError('unsafe test cleanup')
            shutil.rmtree(target)
        self.addCleanup(cleanup)

        def write(name, body):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            raw = body if isinstance(body, bytes) else json.dumps(body).encode('utf-8')
            path.write_bytes(raw)
            return sha256(raw).hexdigest()

        self.pdf_path = 'data/audit/primary.pdf'
        pdf_hash = write(self.pdf_path, b'%PDF-synthetic-test')
        source_url = 'https://www.sse.com.cn/synthetic.pdf'
        review_path = 'research/review.json'
        review_hash = write(review_path, {'events': [
            {'symbol': '511010', 'ex_date': '2026-09-18', 'cash_per_share': '0.6204',
             'payment_date': '2026-09-23', 'publication_date': '2026-09-15',
             'source_url': source_url}]})
        audit_path = 'research/audit.json'
        audit_hash = write(audit_path, {'status': 'SELECTED_FIELDS_MATCH',
                                       'input_sha256': {review_path: review_hash}, 'checks': [
            {'symbol': '511010', 'ex_date': '2026-09-18', 'differences': [],
             'checked_fields': ['ex_date', 'registration_date', 'payment_date', 'cash_per_share']}]})
        manifest_path = 'data/audit/manifest.json'
        manifest_hash = write(manifest_path, {'review_sha256': review_hash, 'records': [
            {'symbol': '511010', 'ex_date': '2026-09-18', 'status': 'ARCHIVED',
             'file': 'primary.pdf', 'url': source_url, 'sha256': pdf_hash,
             'received_at_utc': '2026-09-20T06:00:00+00:00'}]})
        self.catalog = {'status': 'KNOWN_EVENTS_ONLY_NOT_COMPLETE',
                        'full_action_discovery_complete': False, 'capital_authorized': False,
                        'events': [{'symbol': '511010', 'date': '2026-09-18', 'ratio': '1',
                                    'cash_per_old_share': '0.6204', 'payment_date': '2026-09-23',
                                    'publication_date': '2026-09-15',
                                    'source_url': source_url, 'review_path': review_path,
                                    'review_sha256': review_hash, 'audit_path': audit_path,
                                    'audit_sha256': audit_hash,
                                    'archive_manifest_path': manifest_path,
                                    'archive_manifest_sha256': manifest_hash,
                                    'primary_pdf_path': self.pdf_path, 'primary_pdf_sha256': pdf_hash}]}
        self.catalog_path = self.root / 'configs/forward_action_anchors.json'
        write('configs/forward_action_anchors.json', self.catalog)
        self.action = Action('511010', pd.Timestamp('2026-09-18'), 1., 0.6204,
                             pd.Timestamp('2026-09-23'))

    def check(self, actions):
        return verify_known_action_anchors(
            self.root, actions, '2026-09-01', '2026-09-30', ('511010',),
            '2026-09-30T08:00:00+00:00')

    def test_primary_anchored_action_matches(self):
        result = self.check([self.action])
        self.assertEqual(result['matched'], [('511010', '2026-09-18')])
        self.assertFalse(result['full_action_discovery_complete'])

    def test_missing_or_incorrect_action_rejected(self):
        with self.assertRaisesRegex(ValueError, 'known corporate action missing'):
            self.check([])
        wrong = Action('511010', pd.Timestamp('2026-09-18'), 1., 0.6203,
                       pd.Timestamp('2026-09-23'))
        with self.assertRaisesRegex(ValueError, 'known corporate action missing'):
            self.check([wrong])

    def test_changed_primary_pdf_rejected(self):
        (self.root / self.pdf_path).write_bytes(b'%PDF-tampered')
        with self.assertRaisesRegex(ValueError, 'primary PDF changed'):
            self.check([self.action])

    def test_future_archive_rejected(self):
        with self.assertRaisesRegex(ValueError, 'primary archive not available'):
            verify_known_action_anchors(self.root, [self.action], '2026-09-01', '2026-09-30',
                                        ('511010',), '2026-09-19T08:00:00+00:00')


if __name__ == '__main__':
    unittest.main()
