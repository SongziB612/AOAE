"""Synthetic integration fixtures only: no future observation claims."""
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import shutil
from uuid import uuid4
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from aoae.etf_momentum import load_spec
from aoae.forward_journal import ForwardJournal
from aoae.paired_workflow import run_workflow
from aoae.reviewed_day import build_day
from aoae.shadow_cycle import reduce_shadow


class PairedWorkflowTests(unittest.TestCase):
    def setUp(self):
        repo = Path(__file__).resolve().parents[1]
        self.spec = load_spec(repo / 'research/hypotheses/0004-cn-etf-dual-momentum/spec.json')
        self.root = repo / 'data/runtime' / ('workflow-test-' + uuid4().hex)
        self.root.mkdir()
        (self.root / 'configs').mkdir()
        (self.root / 'configs/forward_action_anchors.json').write_text(json.dumps({
            'status': 'KNOWN_EVENTS_ONLY_NOT_COMPLETE', 'events': [],
            'full_action_discovery_complete': False, 'capital_authorized': False}),
            encoding='utf-8')
        def cleanup():
            target = self.root.resolve()
            if target.parent != (repo / 'data/runtime').resolve() or not target.name.startswith('workflow-test-'):
                raise ValueError('unsafe test cleanup')
            shutil.rmtree(target)
        self.addCleanup(cleanup)
        self.calendar = json.loads((repo / 'configs/cn_exchange_calendar_2026.json').read_text())
        self.freeze = {'frozen_at_utc': '2026-09-05T00:00:00+00:00',
                       'arms': ['causal_total_return_momentum_overlay', 'monthly_same_universe_equal_weight',
                                'monthly_same_universe_exposure_matched_equal_weight'],
                       'initial_paper_capital_per_arm_cny': 300000, 'risk_pause_loss_cny': 100000,
                       'capital_authorized': False, 'orders_authorized': False, 'broker_connection_authorized': False}
        self.j = ForwardJournal(self.root / 'test.sqlite3', reducer=reduce_shadow)
        with patch('aoae.forward_journal.datetime') as clock:
            clock.now.return_value = datetime.fromisoformat('2026-09-10T08:00:00+00:00')
            self.j.append('genesis', {'kind': 'SHADOW_INIT', 'freeze': self.freeze})

    def run_day(self, day):
        now = day + 'T09:00:00+00:00'
        with patch('aoae.forward_journal.datetime') as clock, \
             patch('aoae.paired_workflow.load_spec', return_value=self.spec), \
             patch('aoae.reviewed_signal.load_spec', return_value=self.spec):
            clock.now.return_value = datetime.fromisoformat(now)
            return run_workflow(self.root, day, self.calendar, self.j, self.freeze, now)

    def write_bundle(self, day, signal=False):
        folder = self.root / 'research/reviewed_inputs' / day
        folder.mkdir(parents=True, exist_ok=True)
        dates = pd.bdate_range('2025-01-02', '2026-09-30') if signal else pd.to_datetime(['2026-09-30', day])
        prices, hashes, provenance = {}, {}, {}
        def write(name, raw, kind):
            path = folder / name
            path.write_bytes(raw)
            relative = path.relative_to(self.root).as_posix()
            hashes[relative] = sha256(raw).hexdigest()
            provenance[relative] = {'kind': kind, 'sha256': hashes[relative],
                'published_at': day + 'T07:00:00+00:00', 'first_available_at': day + 'T07:01:00+00:00',
                'captured_at': day + 'T07:02:00+00:00'}
            return relative
        for i, symbol in enumerate(self.spec.symbols if signal else self.spec.risk_assets):
            t = np.arange(len(dates))
            close = np.exp(.0002 * (i + 1) * t + .01 * np.sin(t / (i + 2))) * 10
            prices[symbol] = write(symbol + '.csv', pd.DataFrame({'date': dates, 'open': close, 'close': close}).to_csv(index=False).encode(), 'market_data')
        cal = write('calendar.json', json.dumps({'sessions': [str(d.date()) for d in dates] + (['2026-10-08'] if signal else [])}).encode(), 'calendar')
        actions = write('actions.json', json.dumps({'status': 'REVIEWED', 'coverage_start': '2025-01-02', 'coverage_end': day, 'actions': []}).encode(), 'corporate_action')
        bundle = {'prices': prices, 'calendar': cal, 'actions': actions,
                  'signal_day' if signal else 'day': day,
                  'review': {'status': 'REVIEWED', 'reviewed_at': day + 'T08:00:00+00:00',
                             'source_sha256': hashes, 'source_provenance': provenance}}
        path = folder / ('signal-bundle.json' if signal else 'day-bundle.json')
        path.write_text(json.dumps(bundle), encoding='utf-8')
        return bundle, path

    def test_idle_does_not_fake_evaluation_days(self):
        result = self.run_day('2026-09-10')
        self.assertFalse(result['blockers'])
        self.assertEqual(result['comparison']['modeled_days'], 0)
        self.assertEqual(self.j.audit()['events'], 1)

    def test_month_end_missing_bundle_is_failure(self):
        result = self.run_day('2026-09-30')
        self.assertEqual(result['status'], 'BLOCKED_REVIEW_REQUIRED')
        self.assertEqual(self.j.audit()['events'], 1)

    def test_signal_next_session_five_asset_execution_and_restart(self):
        self.write_bundle('2026-09-30', signal=True)
        first = self.run_day('2026-09-30')
        self.assertFalse(first['blockers'], first)
        self.assertEqual(first['comparison']['saved_signals'], 1)
        second = self.run_day('2026-09-30')
        self.assertIn('SIGNAL_ALREADY_RECORDED', second['stages'])
        self.write_bundle('2026-10-08')
        executed = self.run_day('2026-10-08')
        self.assertFalse(executed['blockers'], executed)
        self.assertGreater(sum(a['modeled_fills'] for a in executed['comparison']['arms'].values()), 0)
        self.assertEqual(executed['comparison']['observed_broker_fills'], 0)
        self.assertFalse(executed['comparison']['profitability_established'])
        self.assertEqual(executed['comparison']['monthly_marked_comparisons'][0]['month'], '2026-10')
        self.assertFalse(executed['comparison']['monthly_marked_comparisons'][0]['complete_calendar_month_verified'])
        count = self.j.audit()['events']
        repeated = self.run_day('2026-10-08')
        self.assertIn('DAY_ALREADY_RECORDED', repeated['stages'])
        self.assertEqual(self.j.audit()['events'], count)

    def test_missing_execution_bundle_keeps_signal(self):
        self.write_bundle('2026-09-30', signal=True)
        self.run_day('2026-09-30')
        result = self.run_day('2026-10-08')
        self.assertEqual(result['status'], 'BLOCKED_REVIEW_REQUIRED')
        self.assertIsNotNone(self.j.audit()['state']['pending_signal'])

    def test_tampered_daily_prices_do_not_append(self):
        bundle, _ = self.write_bundle('2026-10-08')
        (self.root / next(iter(bundle['prices'].values()))).write_text('tampered')
        result = self.run_day('2026-10-08')
        self.assertEqual(result['status'], 'BLOCKED_REVIEW_REQUIRED')
        self.assertEqual(self.j.audit()['events'], 1)

    def test_unreviewed_actions_rejected(self):
        bundle, _ = self.write_bundle('2026-10-08')
        bundle['review']['status'] = 'UNKNOWN'
        with self.assertRaises(ValueError):
            build_day(self.root, bundle, self.spec.risk_assets, '2026-10-08T09:00:00+00:00')

    def test_month_end_rejects_stale_action_snapshot(self):
        bundle, path = self.write_bundle('2026-09-30', signal=True)
        provenance = bundle['review']['source_provenance'][bundle['actions']]
        provenance.update(published_at='2026-09-30T06:30:00+00:00',
                          first_available_at='2026-09-30T06:31:00+00:00',
                          captured_at='2026-09-30T06:32:00+00:00')
        path.write_text(json.dumps(bundle), encoding='utf-8')
        result = self.run_day('2026-09-30')
        self.assertEqual(result['status'], 'BLOCKED_REVIEW_REQUIRED')
        self.assertTrue(any('snapshot predates signal close' in b for b in result['blockers']))
        self.assertEqual(self.j.audit()['events'], 1)

    def test_market_closed_does_not_append(self):
        result = self.run_day('2026-10-01')
        self.assertIn('MARKET_CLOSED', result['stages'])
        self.assertEqual(self.j.audit()['events'], 1)
