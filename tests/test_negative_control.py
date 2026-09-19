from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import unittest

from aoae.experiment import canonical_json
from aoae.negative_control import load_negative_control_spec, run_negative_control, wilson_upper_bound_95


SPEC_PATH = Path(__file__).parents[1] / "research" / "experiments" / "0003-iid-negative-control" / "spec.json"


class NegativeControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = load_negative_control_spec(SPEC_PATH)

    def test_seed_source_is_bound_and_complete(self) -> None:
        self.assertEqual(len(self.spec.seeds), 32)

    def test_wilson_upper_bound_for_zero_of_32(self) -> None:
        self.assertEqual(wilson_upper_bound_95(0, 32), 0.107179198255)

    def test_result_is_deterministic(self) -> None:
        self.assertEqual(
            canonical_json(run_negative_control(self.spec)),
            canonical_json(run_negative_control(self.spec)),
        )

    def test_iid_null_is_rejected_without_authorizing_capital(self) -> None:
        record = run_negative_control(self.spec)
        self.assertEqual(record["result"]["status"], "PASS")
        self.assertEqual(record["decision"], "negative_control_rejected")
        self.assertFalse(record["capital_authorized"])

    def test_gate_can_fail_closed(self) -> None:
        strict = replace(self.spec, maximum_wilson_upper_bound=0.05)
        record = run_negative_control(strict)
        self.assertEqual(record["result"]["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
