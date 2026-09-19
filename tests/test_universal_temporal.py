import json
from pathlib import Path
import unittest

import pandas as pd

from aoae.universal_temporal import partition_sessions


class TemporalTests(unittest.TestCase):
    def setUp(self):
        self.protocol = json.loads((Path(__file__).resolve().parents[1] /
            'configs/universal_real_protocol.json').read_text(encoding='utf-8'))
        # Fixture weekdays, NOT claimed to be the exchange calendar.
        self.days = [str(d.date()) for d in pd.bdate_range('2007-01-01', '2025-12-31')]

    def test_disjoint_gapped_partitions(self):
        result = partition_sessions(self.days, self.protocol)
        p, e = result['partitions'], result['excluded']
        self.assertEqual([len(e[k]) for k in ('train', 'validation', 'test')], [21, 42, 21])
        self.assertTrue(p['train'][-1] < p['validation'][0] < p['test'][0])
        self.assertFalse(set(p['train']) & set(p['validation']))

    def test_no_holdout_and_no_duplicates(self):
        for days in (self.days + ['2026-09-07'], self.days + [self.days[-1]]):
            with self.assertRaises(ValueError):
                partition_sessions(days, self.protocol)

    def test_insufficient_partition_fails(self):
        with self.assertRaises(ValueError):
            partition_sessions(self.days[:10], self.protocol)
