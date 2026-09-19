from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import unittest

from aoae.temporal_hypothesis import evaluate_slope_reversal, load_slope_reversal_spec


SPEC_PATH = Path(__file__).parents[1] / "research" / "hypotheses" / "0003-treasury-slope-change-reversal" / "spec.json"


def temporal_xml(reversing: bool, rows: int = 240) -> bytes:
    observed = date(2022, 1, 3)
    spread_bps = 0
    entries = []
    for index in range(rows):
        while observed.weekday() >= 5:
            observed += timedelta(days=1)
        if index:
            if reversing:
                spread_bps += 2 if index % 2 else -2
            else:
                spread_bps += (1, 1, -1, -1)[index % 4]
        two_year = 4 + spread_bps / 200
        ten_year = 4 - spread_bps / 200
        entries.append(
            f"<entry><content><m:properties><d:NEW_DATE>{observed.isoformat()}T00:00:00</d:NEW_DATE>"
            f"<d:BC_2YEAR>{two_year:.3f}</d:BC_2YEAR><d:BC_10YEAR>{ten_year:.3f}</d:BC_10YEAR>"
            "</m:properties></content></entry>"
        )
        observed += timedelta(days=1)
    return (
        '<feed xmlns="http://www.w3.org/2005/Atom" '
        'xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices" '
        'xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata">'
        + "".join(entries) + "</feed>"
    ).encode()


class TemporalHypothesisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = load_slope_reversal_spec(SPEC_PATH)

    def test_contract_uses_past_only_and_forbids_capital(self) -> None:
        self.assertEqual(self.spec.maximum_lag1_correlation, -0.1)
        self.assertFalse(self.spec.strategy_mining_authorized)
        self.assertFalse(self.spec.capital_authorized)

    def test_reversing_fixture_passes(self) -> None:
        record = evaluate_slope_reversal(temporal_xml(reversing=True), self.spec, "abcdef1")
        self.assertEqual(record["result"]["status"], "PASS")
        self.assertAlmostEqual(record["evidence"]["lag1_pearson_correlation"], -1.0)

    def test_persistent_fixture_fails_closed(self) -> None:
        record = evaluate_slope_reversal(temporal_xml(reversing=False), self.spec, "abcdef1")
        self.assertEqual(record["result"]["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
