from __future__ import annotations

from pathlib import Path
import unittest

from aoae.real_hypothesis import evaluate_yield_comovement, load_yield_comovement_spec, pearson_correlation


SPEC_PATH = Path(__file__).parents[1] / "research" / "hypotheses" / "0001-treasury-yield-comovement" / "spec.json"


def correlated_xml(rows: int = 240, opposite: bool = False) -> bytes:
    from datetime import date, timedelta
    entries = []
    observed = date(2025, 1, 1)
    value_2y = 4.0
    value_10y = 4.2
    for index in range(rows):
        while observed.weekday() >= 5:
            observed += timedelta(days=1)
        move = 0.01 if index % 3 else -0.01
        value_2y += move
        value_10y += -move if opposite else move
        entries.append(f"<entry><content><m:properties><d:NEW_DATE>{observed.isoformat()}T00:00:00</d:NEW_DATE><d:BC_2YEAR>{value_2y:.2f}</d:BC_2YEAR><d:BC_10YEAR>{value_10y:.2f}</d:BC_10YEAR></m:properties></content></entry>")
        observed += timedelta(days=1)
    return ('<feed xmlns="http://www.w3.org/2005/Atom" xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices" xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata">' + "".join(entries) + "</feed>").encode()


class RealHypothesisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = load_yield_comovement_spec(SPEC_PATH)

    def test_contract_is_one_trial_without_capital(self) -> None:
        self.assertFalse(self.spec.strategy_mining_authorized)
        self.assertFalse(self.spec.capital_authorized)

    def test_pearson_known_values(self) -> None:
        self.assertAlmostEqual(pearson_correlation([1, 2, 3], [2, 4, 6]), 1.0)
        self.assertAlmostEqual(pearson_correlation([1, 2, 3], [6, 4, 2]), -1.0)

    def test_supported_fixture_passes(self) -> None:
        record = evaluate_yield_comovement(correlated_xml(), self.spec, "abcdef1")
        self.assertEqual(record["result"]["status"], "PASS")

    def test_opposite_fixture_fails_closed(self) -> None:
        record = evaluate_yield_comovement(correlated_xml(opposite=True), self.spec, "abcdef1")
        self.assertEqual(record["result"]["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
