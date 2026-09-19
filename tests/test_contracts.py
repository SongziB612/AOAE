from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from aoae.contracts import ContractError, parse_spec


SPEC_PATH = Path(__file__).parents[1] / "research" / "experiments" / "0001-synthetic-mean-reversion" / "spec.json"


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw = json.loads(SPEC_PATH.read_text(encoding="utf-8"))

    def test_reference_spec_is_valid(self) -> None:
        spec = parse_spec(copy.deepcopy(self.raw))
        self.assertEqual(spec.method.trial_count, 1)
        self.assertFalse(spec.capital_authorized)

    def test_unknown_key_is_rejected(self) -> None:
        raw = copy.deepcopy(self.raw)
        raw["untracked_assumption"] = "silent"
        with self.assertRaisesRegex(ContractError, "unexpected"):
            parse_spec(raw)

    def test_capital_authorization_is_rejected(self) -> None:
        raw = copy.deepcopy(self.raw)
        raw["capital_authorized"] = True
        with self.assertRaisesRegex(ContractError, "capital_authorized"):
            parse_spec(raw)

    def test_zero_lag_signal_is_rejected_as_lookahead(self) -> None:
        raw = copy.deepcopy(self.raw)
        raw["method"]["signal_lag"] = 0
        with self.assertRaisesRegex(ContractError, "signal_lag=1"):
            parse_spec(raw)


if __name__ == "__main__":
    unittest.main()
