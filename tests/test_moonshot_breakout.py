import unittest

import numpy as np
import pandas as pd

from aoae.moonshot_breakout import simulate_breakout


class MoonshotBreakoutTests(unittest.TestCase):
    def test_signal_executes_only_at_following_open_and_uses_lots(self):
        dates = pd.bdate_range("2024-01-01", periods=90)
        rising = np.arange(1.0, 1.0 + len(dates) * 0.01, 0.01)
        closes = pd.DataFrame({"100001": rising, "100002": np.ones(len(dates))}, index=dates)
        opens = closes.copy()
        equity, events, _ = simulate_breakout(
            opens, closes, dates[70].date().isoformat(), dates[-1].date().isoformat(),
            entry_window=10, exit_window=5, rank_window=12,
        )
        entries = [event for event in events if event["type"] == "ENTRY"]
        self.assertTrue(entries)
        self.assertGreater(entries[0]["execution_date"], entries[0]["signal_date"])
        self.assertEqual(entries[0]["quantity"] % 100, 0)
        self.assertTrue((equity > 0).all())


if __name__ == "__main__":
    unittest.main()
