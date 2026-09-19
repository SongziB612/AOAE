from __future__ import annotations

import copy
from dataclasses import replace
import json
from pathlib import Path
import unittest

from aoae.contracts import ContractError
from aoae.experiment import canonical_json
from aoae.sensitivity import run_sensitivity, wilson_lower_bound_95
from aoae.sensitivity_contracts import load_sensitivity_spec, parse_sensitivity_spec


SPEC_PATH = Path(__file__).parents[1] / "research" / "experiments" / "0002-multiseed-sensitivity" / "spec.json"


class SensitivityContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw = json.loads(SPEC_PATH.read_text(encoding="utf-8"))

    def test_reference_spec_and_base_digest_are_valid(self) -> None:
        sensitivity, base = load_sensitivity_spec(SPEC_PATH)
        self.assertEqual(len(sensitivity.seeds), 32)
        self.assertEqual(base.experiment_id, "EXP-0001-synthetic-mean-reversion")

    def test_duplicate_seeds_are_rejected(self) -> None:
        raw = copy.deepcopy(self.raw)
        raw["seeds"][-1] = raw["seeds"][0]
        with self.assertRaisesRegex(ContractError, "duplicates"):
            parse_sensitivity_spec(raw)

    def test_too_few_seeds_are_rejected(self) -> None:
        raw = copy.deepcopy(self.raw)
        raw["seeds"] = raw["seeds"][:5]
        with self.assertRaisesRegex(ContractError, "between 20 and 1000"):
            parse_sensitivity_spec(raw)

    def test_capital_authorization_is_rejected(self) -> None:
        raw = copy.deepcopy(self.raw)
        raw["capital_authorized"] = True
        with self.assertRaisesRegex(ContractError, "capital_authorized"):
            parse_sensitivity_spec(raw)


class SensitivityRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec, cls.base = load_sensitivity_spec(SPEC_PATH)

    def test_wilson_bound_for_all_32_successes(self) -> None:
        self.assertEqual(wilson_lower_bound_95(32, 32), 0.892820801745)

    def test_all_declared_seeds_are_reported_in_order(self) -> None:
        record = run_sensitivity(self.spec, self.base)
        reported = tuple(item["seed"] for item in record["evidence"]["seed_results"])
        self.assertEqual(reported, self.spec.seeds)

    def test_reference_sensitivity_is_deterministic(self) -> None:
        first = canonical_json(run_sensitivity(self.spec, self.base))
        second = canonical_json(run_sensitivity(self.spec, self.base))
        self.assertEqual(first, second)

    def test_passing_gate_does_not_authorize_capital(self) -> None:
        record = run_sensitivity(self.spec, self.base)
        self.assertEqual(record["result"]["status"], "PASS")
        self.assertFalse(record["capital_authorized"])

    def test_gate_fails_when_preregistered_interval_threshold_is_not_met(self) -> None:
        strict_acceptance = replace(
            self.spec.acceptance,
            minimum_seed_pass_rate=1.0,
            minimum_wilson_lower_bound=0.95,
        )
        strict_spec = replace(self.spec, acceptance=strict_acceptance)
        record = run_sensitivity(strict_spec, self.base)
        self.assertEqual(record["result"]["status"], "FAIL")
        self.assertFalse(record["result"]["checks"]["wilson_lower_bound_at_least_minimum"])


if __name__ == "__main__":
    unittest.main()
