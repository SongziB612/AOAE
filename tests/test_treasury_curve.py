from __future__ import annotations

import csv
import io
from pathlib import Path
import unittest

from aoae.treasury_curve import build_canonical_csv, load_derivation_spec


SPEC_PATH = Path(__file__).parents[1] / "research" / "derived_datasets" / "0001-treasury-curve-canonical" / "spec.json"


def two_row_xml() -> bytes:
    source_fields = (
        "BC_1MONTH", "BC_2MONTH", "BC_3MONTH", "BC_4MONTH", "BC_6MONTH",
        "BC_1YEAR", "BC_2YEAR", "BC_3YEAR", "BC_5YEAR", "BC_7YEAR",
        "BC_10YEAR", "BC_20YEAR", "BC_30YEAR",
    )
    rows = []
    for observed, shift in (("2024-01-02", 0), ("2024-01-03", 1)):
        values = {field: 4.00 for field in source_fields}
        values["BC_2YEAR"] = 4.50 + shift / 100
        values["BC_10YEAR"] = 4.00 + shift / 100
        values["BC_3MONTH"] = 5.00
        fields = "".join(f"<d:{field}>{value:.2f}</d:{field}>" for field, value in values.items())
        rows.append(f"<entry><content><m:properties><d:NEW_DATE>{observed}T00:00:00</d:NEW_DATE>{fields}</m:properties></content></entry>")
    return ('<feed xmlns="http://www.w3.org/2005/Atom" xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices" xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata">' + "".join(rows) + "</feed>").encode()


class TreasuryCurveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = load_derivation_spec(SPEC_PATH)

    def test_contract_forbids_strategy_and_capital(self) -> None:
        self.assertEqual(self.spec.strategy_trials, 0)
        self.assertFalse(self.spec.strategy_mining_authorized)
        self.assertFalse(self.spec.capital_authorized)

    def test_canonical_output_is_deterministic(self) -> None:
        first, _ = build_canonical_csv(two_row_xml(), self.spec)
        second, _ = build_canonical_csv(two_row_xml(), self.spec)
        self.assertEqual(first, second)

    def test_spreads_and_changes_are_exact(self) -> None:
        output, analysis = build_canonical_csv(two_row_xml(), self.spec)
        rows = list(csv.DictReader(io.StringIO(output.decode())))
        self.assertEqual(rows[0]["spread_10y_2y_bps"], "-50")
        self.assertEqual(rows[0]["spread_10y_3m_bps"], "-100")
        self.assertEqual(rows[1]["change_10y_bps"], "1")
        self.assertTrue(all(analysis["checks"].values()))

    def test_no_strategy_columns_exist(self) -> None:
        lowered = " ".join(self.spec.columns).lower()
        for prohibited in self.spec.prohibited_columns:
            self.assertNotIn(prohibited, lowered)


if __name__ == "__main__":
    unittest.main()
