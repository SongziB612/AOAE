"""Cross-check Decimal daily engine against unchanged historical float ledger."""
from decimal import Decimal
import unittest
import pandas as pd

from aoae.corporate_action_replay import Action, replay
from aoae.shadow_accounting import advance_day, new_account


class IndependentShadowReplayTests(unittest.TestCase):
    def test_daily_split_dividend_and_rebalances_match_reference(self):
        dates = pd.bdate_range('2025-01-02', periods=20)
        prices = pd.DataFrame({'A': [10.] * 5 + [5.] * 5 + [4.8] * 10,
                               'B': [20 + i / 10 for i in range(20)]}, index=dates)
        opens = prices * 1.001
        actions = [Action('A', dates[5], 2, 0, None, 'floor'),
                   Action('A', dates[10], 1, .2, dates[12], 'floor')]
        schedule = {dates[i]: ({'A': .4, 'B': .3}, {}, dates[i - 1].date().isoformat(), {}) for i in (1, 8, 15)}
        expected, orders, _ = replay(opens, prices, schedule, actions, ('A', 'B'), dates[1], dates[-1],
                                     initial=10000, pause_loss=1000, use_payment_dates=True)
        state = new_account(10000, 1000)
        count = 0
        for i in range(1, len(dates)):
            day = dates[i]
            events = [{'id': str(n), 'symbol': a.symbol, 'date': str(a.date.date()), 'ratio': a.ratio,
                       'cash_per_old_share': a.cash_per_old_share, 'payment_date': str(a.payment_date.date()) if a.payment_date is not None else None,
                       'rounding': a.rounding} for n, a in enumerate(actions) if a.date == day]
            state, fills = advance_day(state, str(day.date()), str(dates[i - 1].date()),
                                       opens.loc[day].to_dict(), prices.loc[day].to_dict(), prices.iloc[i - 1].to_dict(),
                                       events, schedule[day][0] if day in schedule else None)
            self.assertLess(abs(float(Decimal(state['equity'])) - expected.loc[day]), 1e-8)
            count += len(fills)
        self.assertEqual(count, len(orders))
