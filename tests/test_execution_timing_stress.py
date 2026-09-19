import unittest
import pandas as pd
from aoae.corporate_action_replay import replay


class ExecutionTimingStressTests(unittest.TestCase):
    def test_close_is_fill_not_signal_or_sizing_price(self):
        dates = pd.date_range('2024-01-01', periods=3)
        closes = pd.DataFrame({'A': [10., 12., 13.]}, index=dates)
        opens = pd.DataFrame({'A': [10., 10., 12.]}, index=dates)
        schedule = {dates[1]: ({'A': .5}, {}, str(dates[0].date()), {})}
        args = (closes, schedule, [], ['A'], str(dates[1].date()), str(dates[-1].date()))
        early, orders, _ = replay(opens, *args, initial=10000., commission=0., slippage_bps=0.)
        late, delayed, _ = replay(closes, *args, initial=10000., commission=0., slippage_bps=0.)
        self.assertEqual(orders[0]['quantity'], 500)
        self.assertEqual(delayed[0]['quantity'], 500)
        self.assertEqual(delayed[0]['price'], 12.)
        self.assertEqual(early.iloc[0]-late.iloc[0], 1000.)

    def test_future_price_change_does_not_change_prior_fill(self):
        dates = pd.date_range('2024-01-01', periods=3)
        closes = pd.DataFrame({'A': [10., 12., 13.]}, index=dates)
        schedule = {dates[1]: ({'A': .5}, {}, str(dates[0].date()), {})}
        def run(frame):
            return replay(frame, frame, schedule, [], ['A'], str(dates[1].date()), str(dates[-1].date()), initial=10000., commission=0., slippage_bps=0.)[1]
        first = run(closes)
        closes.iloc[-1, 0] = 130.
        self.assertEqual(first, run(closes))
