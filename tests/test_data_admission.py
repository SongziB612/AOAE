from __future__ import annotations

from pathlib import Path
import unittest

from aoae.data_admission import audit_treasury_xml, load_data_admission_spec


SPEC_PATH = Path(__file__).parents[1] / "research" / "data_admissions" / "0001-us-treasury-yield-curve" / "spec.json"


def fixture_xml(rows: int = 240, missing_field: bool = False) -> bytes:
    fields = [
        "BC_1MONTH", "BC_2MONTH", "BC_3MONTH", "BC_4MONTH", "BC_6MONTH",
        "BC_1YEAR", "BC_2YEAR", "BC_3YEAR", "BC_5YEAR", "BC_7YEAR",
        "BC_10YEAR", "BC_20YEAR", "BC_30YEAR",
    ]
    entries = []
    day = 1
    produced = 0
    while produced < rows:
        from datetime import date, timedelta
        observed = date(2024, 1, 1) + timedelta(days=day - 1)
        day += 1
        if observed.weekday() >= 5:
            continue
        values = "".join(
            f"<d:{field}>{'' if missing_field and field == 'BC_30YEAR' else '4.25'}</d:{field}>"
            for field in fields
        )
        entries.append(f"<entry><content><m:properties><d:NEW_DATE>{observed.isoformat()}T00:00:00</d:NEW_DATE>{values}</m:properties></content></entry>")
        produced += 1
    xml = '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices" xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata">' + "".join(entries) + "</feed>"
    return xml.encode()


class DataAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = load_data_admission_spec(SPEC_PATH)

    def test_contract_disables_strategy_mining_and_capital(self) -> None:
        self.assertEqual(self.spec.strategy_trials, 0)
        self.assertFalse(self.spec.strategy_mining_authorized)
        self.assertFalse(self.spec.capital_authorized)

    def test_valid_fixture_is_admitted(self) -> None:
        record = audit_treasury_xml(fixture_xml(), self.spec)
        self.assertEqual(record["result"]["status"], "PASS")

    def test_missing_required_field_fails_closed(self) -> None:
        record = audit_treasury_xml(fixture_xml(missing_field=True), self.spec)
        self.assertEqual(record["result"]["status"], "FAIL")
        self.assertFalse(record["result"]["checks"]["required_field_coverage"])


if __name__ == "__main__":
    unittest.main()
