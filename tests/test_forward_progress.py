import unittest

from aoae.forward_progress import summarize_forward_progress


class ForwardProgressTests(unittest.TestCase):
    def test_waiting_state_without_rebalance(self):
        result = summarize_forward_progress([
            {"as_of": "2026-09-07", "equity_cny": 10000, "drawdown_fraction": 0, "events": [], "last_run": {"processed_market_days": 1}}
        ], "2026-09-04", "2026-12-04", 10000)
        self.assertEqual(result["processed_new_market_days"], 1)
        self.assertIsNone(result["first_order_lot_feasible"])
        self.assertFalse(result["review_date_elapsed"])

    def test_rebalance_is_deduplicated_across_cumulative_snapshots(self):
        event = {"type": "PAPER_MONTHLY_REBALANCE", "signal_date": "2026-09-30", "date": "2026-10-08", "legs": [{"quantity": 100}]}
        result = summarize_forward_progress([
            {"as_of": "2026-10-08", "equity_cny": 9900, "drawdown_fraction": -.01, "events": [event], "last_run": {"processed_market_days": 1}},
            {"as_of": "2026-10-09", "equity_cny": 9950, "drawdown_fraction": -.005, "events": [event], "last_run": {"processed_market_days": 1}},
        ], "2026-09-04", "2026-12-04", 10000)
        self.assertEqual(result["generated_rebalances"], 1)
        self.assertTrue(result["first_order_lot_feasible"])
        self.assertEqual(result["maximum_drawdown_fraction"], -.01)

    def test_review_date_changes_status_without_authorizing_capital(self):
        result = summarize_forward_progress([
            {"as_of": "2026-12-04", "equity_cny": 10100, "events": [], "last_run": {"processed_market_days": 1}}
        ], "2026-09-04", "2026-12-04", 10000)
        self.assertEqual(result["status"], "READY_FOR_SCHEDULED_REVIEW")


if __name__ == "__main__":
    unittest.main()
