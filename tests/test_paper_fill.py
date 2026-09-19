import unittest

from aoae.paper_fill import apply_market_message, summarize_leg_risk


def legs():
    return {
        "a": {"paper_bid": .40, "cross_events": 0, "trade_events_at_or_below_bid": 0, "first_fill_evidence_at_utc": None, "first_fill_evidence_source": None},
        "b": {"paper_bid": .50, "cross_events": 0, "trade_events_at_or_below_bid": 0, "first_fill_evidence_at_utc": None, "first_fill_evidence_source": None},
    }


class PaperFillTests(unittest.TestCase):
    def test_price_change_nested_asset_is_counted(self):
        state = legs()
        apply_market_message({"event_type": "price_change", "timestamp": "1000", "price_changes": [{"asset_id": "a", "best_ask": ".40"}]}, state)
        self.assertEqual(state["a"]["cross_events"], 1)
        self.assertEqual(state["a"]["first_fill_evidence_source"], "price_change.best_ask")

    def test_price_above_quote_is_not_evidence(self):
        state = legs()
        apply_market_message({"event_type": "best_bid_ask", "asset_id": "a", "best_ask": ".41", "timestamp": "1000"}, state)
        self.assertEqual(state["a"]["cross_events"], 0)

    def test_sell_trade_at_bid_is_counted(self):
        state = legs()
        apply_market_message({"event_type": "last_trade_price", "asset_id": "b", "side": "SELL", "price": ".50", "timestamp": "2000"}, state)
        self.assertEqual(state["b"]["trade_events_at_or_below_bid"], 1)

    def test_partial_fill_reports_worst_case_spend(self):
        state = legs()
        apply_market_message({"event_type": "price_change", "timestamp": "1000", "price_changes": [{"asset_id": "a", "best_ask": ".39"}]}, state)
        result = summarize_leg_risk(state)
        self.assertEqual(result["legs_with_fill_evidence"], 1)
        self.assertAlmostEqual(result["worst_case_loss_if_only_evidenced_legs_fill"], .40)

    def test_all_legs_reports_completion_lag(self):
        state = legs()
        apply_market_message({"event_type": "price_change", "timestamp": "1000", "price_changes": [{"asset_id": "a", "best_ask": ".40"}]}, state)
        apply_market_message({"event_type": "price_change", "timestamp": "3500", "price_changes": [{"asset_id": "b", "best_ask": ".50"}]}, state)
        result = summarize_leg_risk(state)
        self.assertTrue(result["all_legs_with_fill_evidence"])
        self.assertAlmostEqual(result["first_to_final_leg_evidence_seconds"], 2.5)
        self.assertEqual(result["worst_case_loss_if_only_evidenced_legs_fill"], 0.0)


if __name__ == "__main__":
    unittest.main()
