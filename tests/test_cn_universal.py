import unittest
import numpy as np
import pandas as pd
from aoae.cn_universal import monthly_schedules, simplex_lattice


class CNUniversalTests(unittest.TestCase):
    def test_symmetric_simplex_grid(self):
        grid = simplex_lattice(5, 4)
        self.assertEqual(grid.shape, (70, 5))
        np.testing.assert_allclose(grid.sum(axis=1), 1)
        np.testing.assert_allclose(grid.mean(axis=0), .2)

    def test_next_session_and_no_current_future_leak(self):
        dates = pd.bdate_range('2021-12-30', '2022-04-08')
        index = pd.DataFrame({'A': np.linspace(1, 2, len(dates)), 'B': 1.}, index=dates)
        args = (('A', 'B'), '2022-01-01', '2022-03-31', 4)
        first = monthly_schedules(index, *args)
        day = pd.Timestamp('2022-02-01')
        changed = index.copy()
        changed.loc[day:, 'A'] *= 10
        second = monthly_schedules(changed, *args)
        self.assertEqual(first['up_monthly'][day][0], second['up_monthly'][day][0])
        self.assertEqual(len(first['equal_buy_hold']), 1)
        self.assertEqual(len(first['up_monthly']), 3)
        for date, row in first['up_monthly'].items():
            self.assertEqual(pd.Timestamp(row[2]), dates[dates.get_loc(date) - 1])

    def test_reset_initial_prior(self):
        dates = pd.bdate_range('2021-12-30', '2022-04-08')
        index = pd.DataFrame({'A': 100., 'B': 1.}, index=dates)
        schedules = monthly_schedules(index, ('A', 'B'), '2022-01-01', '2022-03-31', 4)
        self.assertEqual(next(iter(schedules['up_monthly'].values()))[0], {'A': .5, 'B': .5})
