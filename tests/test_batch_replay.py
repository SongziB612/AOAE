import unittest

from aoae.batch_replay import compare_points, replay_points, simulate_taker


class BatchReplayTests(unittest.TestCase):
    def record(self):
        return {
            "market": {"end_epoch": 3},
            "fee": {"rate": .07, "exponent": 1},
            "reference": {"opening_tick": {"value": 100}, "closing_tick": {"value": 102}},
            "evidence": {"book_snapshots": [
                {"timestamp_ms": 1000, "reference_price": 99, "up_ask": .4, "up_ask_size": 5, "down_ask": .6, "down_ask_size": 5},
                {"timestamp_ms": 2000, "reference_price": 101, "up_ask": .7, "up_ask_size": 5, "down_ask": .3, "down_ask_size": 5},
                {"timestamp_ms": 2600, "reference_price": 101, "up_ask": .8, "up_ask_size": 5, "down_ask": .2, "down_ask_size": 5},
            ]},
        }

    def test_replay_is_independent_and_comparable(self):
        points = replay_points(self.record(), [2, 1])
        self.assertFalse(points[0]["signal_correct"])
        self.assertTrue(points[1]["signal_correct"])
        self.assertEqual(compare_points(points, points), [])
        changed = [dict(point) for point in points]
        changed[1]["ask"] += .01
        self.assertTrue(compare_points(points, changed))

    def test_execution_reprices_and_applies_slippage(self):
        point = replay_points(self.record(), [1])[0]
        result = simulate_taker(self.record(), point, 500, 5, .01)
        self.assertEqual(result["status"], "SIMULATED_REPRICE")
        self.assertEqual(result["actual_delay_ms"], 600)
        self.assertAlmostEqual(result["execution_price"], .81)


if __name__ == "__main__":
    unittest.main()
