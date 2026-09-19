import unittest

from aoae.manual_execution import prepare_manual_packet, reconcile_manual_fills


def snapshot():
    return {
        "account_id": "PAPER-0004",
        "events": [{
            "type": "PAPER_MONTHLY_REBALANCE",
            "signal_date": "2026-09-30",
            "date": "2026-10-08",
            "legs": [{"symbol": "159915", "side": "BUY", "quantity": 200, "paper_fill_open": 3.2}],
        }],
    }


class ManualExecutionTests(unittest.TestCase):
    def test_packet_requires_live_price_and_human_approval(self):
        packet = prepare_manual_packet(snapshot())
        self.assertIsNone(packet["legs"][0]["live_limit_price"])
        self.assertFalse(packet["orders_authorized"])

    def test_missing_signal_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "no clean monthly"):
            prepare_manual_packet({"account_id": "x", "events": []})

    def test_partial_fill_is_not_auto_completed(self):
        packet = prepare_manual_packet(snapshot())
        packet["legs"][0]["live_limit_price"] = 3.21
        result = reconcile_manual_fills(packet, [{"symbol": "159915", "side": "BUY", "quantity": 100, "price": 3.2, "commission_cny": 5}])
        self.assertEqual(result["status"], "PARTIAL")
        self.assertFalse(result["automatic_follow_up_allowed"])

    def test_wrong_side_and_limit_violation_are_detected(self):
        packet = prepare_manual_packet(snapshot())
        packet["legs"][0]["live_limit_price"] = 3.2
        wrong = reconcile_manual_fills(packet, [{"symbol": "159915", "side": "SELL", "quantity": 100, "price": 3.2}])
        self.assertEqual(wrong["status"], "VIOLATION")
        above = reconcile_manual_fills(packet, [{"symbol": "159915", "side": "BUY", "quantity": 200, "price": 3.21}])
        self.assertEqual(above["status"], "VIOLATION")


if __name__ == "__main__":
    unittest.main()
