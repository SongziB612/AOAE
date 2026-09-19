import json
from pathlib import Path
import unittest
from aoae.exchange_calendar import day_plan, latest_closed_session


class ExchangeCalendarTests(unittest.TestCase):
    def setUp(self):
        self.c = json.loads((Path(__file__).resolve().parents[1] / 'configs/cn_exchange_calendar_2026.json').read_text())

    def test_september_month_end(self):
        p = day_plan(self.c, '2026-09-30')
        self.assertEqual(p['next_session'], '2026-10-08')
        self.assertEqual(p['signal_schedule'], 'MONTH_END_SIGNAL_DUE')

    def test_september_tenth_not_due(self):
        self.assertEqual(day_plan(self.c, '2026-09-10')['signal_schedule'], 'NOT_A_SIGNAL_DAY')

    def test_working_weekend_still_market_closed(self):
        self.assertFalse(day_plan(self.c, '2026-09-20')['is_session'])
        self.assertFalse(day_plan(self.c, '2026-10-10')['is_session'])

    def test_holidays(self):
        self.assertEqual(day_plan(self.c, '2026-09-25')['next_session'], '2026-09-28')
        self.assertFalse(day_plan(self.c, '2026-10-01')['is_session'])

    def test_no_future_year_extrapolation(self):
        with self.assertRaises(ValueError):
            day_plan(self.c, '2027-01-04')
        self.assertEqual(day_plan(self.c, '2026-12-31')['signal_schedule'], 'NEXT_SESSION_UNREVIEWED')

    def test_weekend_recovers_friday(self):
        self.assertEqual(latest_closed_session(self.c, '2026-09-12T12:30:00+00:00'), '2026-09-11')

    def test_preclose_does_not_capture_incomplete_day(self):
        self.assertEqual(latest_closed_session(self.c, '2026-09-14T06:59:59+00:00'), '2026-09-11')
        self.assertEqual(latest_closed_session(self.c, '2026-09-14T07:00:00+00:00'), '2026-09-14')

    def test_holiday_recovers_last_session(self):
        self.assertEqual(latest_closed_session(self.c, '2026-10-05T12:00:00+00:00'), '2026-09-30')

    def test_unknown_or_naive_clock_rejected(self):
        for at in ('2027-01-04T12:00:00+00:00', '2026-09-12T12:00:00', '2026-01-01T12:00:00+00:00'):
            with self.assertRaises(ValueError):
                latest_closed_session(self.c, at)
