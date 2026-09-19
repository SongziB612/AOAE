import unittest
import pandas as pd
from aoae.daily_snapshot import validate_daily_frame


class DailySnapshotTests(unittest.TestCase):
    def setUp(self):
        self.frame = pd.DataFrame([dict(date='2026-09-14', open=4, high=5, low=3,
                                        close=4.5, volume=100, amount=450)])

    def check(self, frame):
        return validate_daily_frame(frame, '2026-09-14', '2026-09-15')

    def test_valid_but_stale_is_not_relabelled(self):
        self.assertEqual(str(self.check(self.frame).date.iloc[-1].date()), '2026-09-14')

    def test_bad_numeric_and_ranges(self):
        for column, value in [('open', float('inf')), ('close', 0), ('low', 4.6),
                              ('high', 4.1), ('volume', -1), ('amount', float('nan'))]:
            with self.subTest(column=column):
                frame = self.frame.copy()
                frame[column] = value
                with self.assertRaises(ValueError):
                    self.check(frame)

    def test_duplicate_and_order(self):
        with self.assertRaises(ValueError):
            self.check(pd.concat([self.frame, self.frame]))
        second = self.frame.copy()
        second['date'] = '2026-09-15'
        with self.assertRaises(ValueError):
            self.check(pd.concat([second, self.frame]))

    def test_intraday_and_missing_overlap(self):
        for date in ('2026-09-14 12:00', '2026-09-15', None):
            with self.subTest(date=date):
                frame = self.frame.copy()
                frame['date'] = date
                with self.assertRaises(ValueError):
                    self.check(frame)
