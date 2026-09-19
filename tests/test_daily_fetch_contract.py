from __future__ import annotations

from pathlib import Path
import unittest


class DailyCycleContractTests(unittest.TestCase):
    def test_cycle_is_local_paper_only(self):
        text = Path("scripts/daily_paper_cycle.ps1").read_text(encoding="utf-8")
        self.assertIn("run_paper_eod.py", text)
        self.assertNotIn("broker", text.lower())
        self.assertNotIn("order", text.lower())
        self.assertIn("snapshot_exists", text)
        self.assertIn("0004-3000-live-pilot-shadow", text)
        self.assertIn("pilot_3000_snapshots", text)

    def test_daily_fetch_does_not_contain_trading_calls(self):
        text = Path("scripts/fetch_sina_daily_prices.py").read_text(encoding="utf-8").lower()
        self.assertNotIn("place_order", text)
        self.assertNotIn("submit_order", text)
        self.assertIn('"orders_authorized": false', text)
        self.assertIn("incomplete cross-asset close", text)
