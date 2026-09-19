import copy
import unittest

from aoae.predictability_state import FEATURE_NAMES, extract_predictability_state


def fixture():
    ticks = []
    for index in range(41):
        ticks.append({"timestamp_ms": 1000 * index, "received_timestamp_ms": 1000 * index + 100, "value": 100 + index * .01})
    snapshots = []
    for timestamp in range(20_000, 40_001, 250):
        snapshots.append({"timestamp_ms": timestamp, "up_bid": .54, "up_ask": .55, "up_ask_size": 8, "down_bid": .44, "down_ask": .46, "down_ask_size": 6})
    return {
        "market": {"slug": "m"},
        "reference": {"opening_tick": {"value": 100}},
        "decision_points": [{"seconds_before_end": 120, "status": "QUOTED_ONLY", "signal": "Up", "signal_correct": True, "snapshot_timestamp_ms": 40_000}],
        "evidence": {"chainlink_ticks": ticks, "book_snapshots": snapshots},
    }


class PredictabilityStateTests(unittest.TestCase):
    def test_extracts_fixed_feature_set(self):
        result = extract_predictability_state(fixture())
        self.assertTrue(result["eligible"])
        self.assertEqual(tuple(result["features"]), FEATURE_NAMES)

    def test_future_received_tick_cannot_change_state(self):
        base = fixture()
        first = extract_predictability_state(base)["features"]
        changed = copy.deepcopy(base)
        changed["evidence"]["chainlink_ticks"].append({"timestamp_ms": 39_000, "received_timestamp_ms": 40_001, "value": 1_000_000})
        self.assertEqual(extract_predictability_state(changed)["features"], first)

    def test_requires_minimum_depth(self):
        data = fixture()
        data["evidence"]["book_snapshots"][-1]["up_ask_size"] = 4
        self.assertEqual(extract_predictability_state(data)["reason"], "insufficient_initial_depth")


if __name__ == "__main__":
    unittest.main()
