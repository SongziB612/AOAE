from copy import deepcopy
import unittest
from aoae.minute_diagnostics import inspect_bars


def rows():
    return [{'day': '2026-09-14 '+t, 'open': str(p), 'high': str(p), 'low': str(p), 'close': str(p), 'volume': '100'}
            for t, p in [('09:31:00', 10), ('09:32:00', 10.01), ('09:36:00', 10.02)]]


class MinuteDiagnosticTests(unittest.TestCase):
    def test_proxy_and_gaps_not_filled(self):
        d = inspect_bars(rows(), '2026-09-14T16:00:00+08:00')[0]
        self.assertEqual(d['signed_close_to_close_proxy_bps'], {'1': '10.000', '5': '20.000'})
        self.assertEqual(len(d['missing_continuous_grid_labels']), 237)

    def test_missing_or_zero_volume_anchor_not_scored(self):
        r = rows()
        r[1]['volume'] = '0'
        self.assertFalse(inspect_bars(r, '2026-09-14T16:00:00+08:00')[0]['anchor_eligible'])
        self.assertFalse(inspect_bars(rows()[:2], '2026-09-14T16:00:00+08:00')[0]['anchor_eligible'])

    def test_invalid_future_and_duplicate_rejected(self):
        cases = [rows()+[rows()[-1]], rows()[::-1]]
        r = deepcopy(rows()); r[0]['high'] = '9'; cases.append(r)
        r = deepcopy(rows()); r[0]['volume'] = 'NaN'; cases.append(r)
        for r in cases:
            with self.assertRaises(ValueError):
                inspect_bars(r, '2026-09-14T16:00:00+08:00')
        with self.assertRaises(ValueError):
            inspect_bars(rows(), '2026-09-14T09:30:00+08:00')
