import unittest
from unittest.mock import patch
from pathlib import Path
from hashlib import sha256
import json
import numpy as np
import pandas as pd
from aoae.etf_momentum import load_spec
from aoae.reviewed_signal import month_end_pair, build_event


class ReviewedSignalTests(unittest.TestCase):
    def test_month_end_pair(self):
        self.assertEqual(month_end_pair(['2026-09-29', '2026-09-30', '2026-10-08'], '2026-09-30'), '2026-10-08')

    def test_not_month_end(self):
        with self.assertRaises(ValueError):
            month_end_pair(['2026-09-29', '2026-09-30'], '2026-09-29')

    def test_incomplete_calendar(self):
        with self.assertRaises(ValueError):
            month_end_pair(['2026-09-30'], '2026-09-30')

    def test_duplicate_calendar(self):
        with self.assertRaises(ValueError):
            month_end_pair(['2026-09-30', '2026-09-30', '2026-10-08'], '2026-09-30')

    def test_full_reviewed_bundle_computes_weights_and_rejects_late(self):
        root = Path(__file__).resolve().parents[1]
        spec = load_spec(root / 'research/hypotheses/0004-cn-etf-dual-momentum/spec.json')
        dates = pd.bdate_range('2025-01-02', '2026-09-30')
        # Synthetic calendar/data fixture, not real source evidence.
        files, prices = {}, {}
        for i, s in enumerate(spec.symbols):
            name = s + '.csv'
            t = np.arange(len(dates))
            files[name] = pd.DataFrame({'date': dates, 'close': np.exp(.0002 * (i + 1) * t + .01 * np.sin(t / (i + 2)))}).to_csv(index=False).encode()
            prices[s] = name
        files['calendar.json'] = json.dumps({'sessions': [str(d.date()) for d in dates] + ['2026-10-08']}).encode()
        files['actions.json'] = json.dumps({'status': 'REVIEWED', 'coverage_start': '2025-01-02', 'coverage_end': '2026-09-30', 'actions': []}).encode()
        hashes = {n: sha256(v).hexdigest() for n, v in files.items()}
        review = {'status': 'REVIEWED', 'reviewed_at': '2026-09-30T07:03:00+00:00', 'source_sha256': hashes,
                  'source_provenance': {n: {'sha256': h, 'kind': 'market_data' if n.endswith('.csv') else 'calendar' if n == 'calendar.json' else 'corporate_action',
                    'published_at': '2026-09-30T07:00:00+00:00', 'first_available_at': '2026-09-30T07:01:00+00:00', 'captured_at': '2026-09-30T07:02:00+00:00'} for n, h in hashes.items()}}
        bundle = {'review': review, 'prices': prices, 'calendar': 'calendar.json', 'actions': 'actions.json', 'signal_day': '2026-09-30'}
        freeze = {'frozen_at_utc': '2026-09-05T00:00:00+00:00', 'arms': ['causal_total_return_momentum_overlay', 'monthly_same_universe_equal_weight', 'monthly_same_universe_exposure_matched_equal_weight']}
        with patch('aoae.reviewed_signal.load_spec', return_value=spec), patch.object(Path, 'read_bytes', lambda p: files[p.name]):
            event = build_event(root, bundle, freeze, '2026-09-30T08:00:00+00:00')
            self.assertEqual(event['kind'], 'PRESAVE_SIGNAL')
            self.assertEqual(set(event['signal']['weights']), set(freeze['arms']))
            self.assertEqual(event['signal']['weights']['monthly_same_universe_equal_weight'], {s: .2 for s in spec.risk_assets})
            with self.assertRaises(ValueError):
                build_event(root, bundle, freeze, '2026-10-08T03:00:00+00:00')
            review['source_sha256']['actions.json'] = 'a' * 64
            with self.assertRaises(ValueError):
                build_event(root, bundle, freeze, '2026-09-30T08:00:00+00:00')
