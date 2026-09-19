import json
import unittest

from aoae.latency_probe import evaluate_decision_points, parse_chainlink_ticks, simulate_delayed_taker, taker_fee_per_share, websocket_capture_is_technically_complete


class LatencyProbeTests(unittest.TestCase):
    def test_parses_direct_and_historical_payloads(self):
        direct = {"topic": "crypto_prices_chainlink", "timestamp": 10, "payload": {"symbol": "bnb/usd", "timestamp": 9, "value": 700.5}}
        self.assertEqual(parse_chainlink_ticks(json.dumps(direct), "BNB/USD")[0]["timestamp_ms"], 9)
        historical = {"topic": "crypto_prices_chainlink", "payload": {"symbol": "bnb/usd", "data": [{"timestamp": 8, "value": 700.0}]}}
        self.assertEqual(parse_chainlink_ticks(json.dumps(historical), "bnb/usd")[0]["value"], 700.0)

    def test_ignores_other_topics_and_symbols(self):
        self.assertEqual(parse_chainlink_ticks('{"topic":"activity","payload":{}}', "bnb/usd"), [])
        self.assertEqual(parse_chainlink_ticks("PONG", "bnb/usd"), [])
        self.assertEqual(parse_chainlink_ticks("not-json", "bnb/usd"), [])
        raw = '{"topic":"crypto_prices_chainlink","payload":{"symbol":"btc/usd","timestamp":1,"value":1}}'
        self.assertEqual(parse_chainlink_ticks(raw, "bnb/usd"), [])

    def test_fee_formula(self):
        self.assertAlmostEqual(taker_fee_per_share(0.5, 0.07), 0.0175)

    def test_all_preregistered_points_are_reported(self):
        rows = [
            {"timestamp_ms": 1000, "reference_price": 99, "up_ask": .4, "down_ask": .61},
            {"timestamp_ms": 2000, "reference_price": 101, "up_ask": .7, "down_ask": .31},
        ]
        result = evaluate_decision_points(rows, 100, 102, 3000, [2, 1], .07)
        self.assertEqual([item["seconds_before_end"] for item in result], [2, 1])
        self.assertFalse(result[0]["signal_correct"])
        self.assertTrue(result[1]["signal_correct"])
        self.assertLess(result[1]["quoted_net_pnl_per_share"], .3)

    def test_delayed_taker_reprices_and_requires_depth(self):
        snapshots = [
            {"timestamp_ms": 1000, "up_ask": .4, "up_ask_size": 5},
            {"timestamp_ms": 1600, "up_ask": .6, "up_ask_size": 5},
        ]
        point = {"status": "QUOTED_ONLY", "signal": "Up", "signal_correct": True, "snapshot_timestamp_ms": 1000}
        result = simulate_delayed_taker(snapshots, point, 500, 5, .07)
        self.assertEqual(result["price"], .6)
        self.assertEqual(result["actual_sample_delay_ms"], 600)
        snapshots[0]["up_ask_size"] = 4
        self.assertEqual(simulate_delayed_taker(snapshots, point, 0, 5, .07)["status"], "INSUFFICIENT_INITIAL_DEPTH")

    def test_no_ask_is_valid_observation_but_missing_transport_is_not(self):
        record = {
            "method": {"book_transport": "websocket"},
            "reference": {"opening_tick": {"value": 1}, "closing_tick": {"value": 2}},
            "evidence": {"book_snapshots": [{"timestamp_ms": 1}]},
            "decision_points": [
                {"seconds_before_end": 60, "status": "QUOTED_ONLY"},
                {"seconds_before_end": 5, "status": "NO_ASK"},
            ],
            "diagnostics": {"book_message_counts": {"PONG": 2, "book": 1}},
        }
        self.assertTrue(websocket_capture_is_technically_complete(record, [60, 5]))
        record["diagnostics"]["book_message_counts"] = {"PONG": 2}
        self.assertFalse(websocket_capture_is_technically_complete(record, [60, 5]))

    def test_legacy_rest_capture_does_not_require_websocket_message_counts(self):
        record = {
            "method": {"book_transport": "rest"},
            "reference": {"opening_tick": {"value": 1}, "closing_tick": {"value": 2}},
            "evidence": {"book_snapshots": [{"timestamp_ms": 1}]},
            "decision_points": [
                {"seconds_before_end": 60, "status": "QUOTED_ONLY"},
                {"seconds_before_end": 5, "status": "NO_ASK"},
            ],
            "diagnostics": {"book_message_counts": {}},
        }
        self.assertTrue(websocket_capture_is_technically_complete(record, [60, 5]))


if __name__ == "__main__":
    unittest.main()
