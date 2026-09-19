from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import unittest

from aoae.slope_hypothesis import evaluate_slope_structure, load_slope_structure_spec


SPEC_PATH = Path(__file__).parents[1] / "research" / "hypotheses" / "0002-treasury-slope-inversion" / "spec.json"


def slope_xml(inverted: bool, rows: int = 240) -> bytes:
    entries = []
    observed = date(2023, 1, 2)
    for index in range(rows):
        while observed.weekday() >= 5:
            observed += timedelta(days=1)
        two_year = 4.50 + (index % 5) / 100
        ten_year = two_year - 0.50 if inverted else two_year + 0.50
        entries.append(
            f"<entry><content><m:properties><d:NEW_DATE>{observed.isoformat()}T00:00:00</d:NEW_DATE>"
            f"<d:BC_2YEAR>{two_year:.2f}</d:BC_2YEAR><d:BC_10YEAR>{ten_year:.2f}</d:BC_10YEAR>"
            "</m:properties></content></entry>"
        )
        observed += timedelta(days=1)
    return (
        '<feed xmlns="http://www.w3.org/2005/Atom" '
        'xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices" '
        'xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata">'
        + "".join(entries) + "</feed>"
    ).encode()


class SlopeHypothesisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = load_slope_structure_spec(SPEC_PATH)

    def test_contract_is_one_trial_without_capital(self) -> None:
        self.assertEqual(self.spec.minimum_inversion_rate, 0.8)
        self.assertFalse(self.spec.strategy_mining_authorized)
        self.assertFalse(self.spec.capital_authorized)

    def test_persistent_inversion_fixture_passes(self) -> None:
        record = evaluate_slope_structure(slope_xml(inverted=True), self.spec, "abcdef1")
        self.assertEqual(record["result"]["status"], "PASS")
        self.assertEqual(record["evidence"]["inversion_rate"], 1.0)

    def test_non_inverted_fixture_fails_closed(self) -> None:
        record = evaluate_slope_structure(slope_xml(inverted=False), self.spec, "abcdef1")
        self.assertEqual(record["result"]["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
