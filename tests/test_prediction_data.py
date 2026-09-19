import json
from pathlib import Path
import unittest

from aoae.contracts import ContractError
from aoae.prediction_data import audit_public_event_payload, load_public_event_spec


SPEC = Path(__file__).parents[1] / "research" / "data_admissions" / "0002-polymarket-active-events" / "spec.json"


def payload(event_id="e1", market_id="m1", closed=False):
    return json.dumps({"events": [{"id": event_id, "slug": "event", "title": "Event", "closed": closed, "markets": [{"id": market_id, "slug": "market", "question": "Will it happen?", "conditionId": "c1", "clobTokenIds": "[]"}]}], "next_cursor": "cursor"}).encode()


class PublicEventDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load_public_event_spec(SPEC)

    def audit(self, data):
        return audit_public_event_payload(data, self.spec, "2026-09-03T12:00:00Z", "Thu, 03 Sep 2026 12:00:01 GMT", "abcdef1")

    def test_valid_payload_passes_without_trials_or_capital(self):
        record = self.audit(payload())
        self.assertEqual(record["result"]["status"], "PASS")
        self.assertEqual(record["research_activity"], {"strategy_trials": 0, "model_trials": 0, "orders": 0})
        self.assertFalse(record["capital_authorized"])

    def test_closed_event_fails(self):
        self.assertEqual(self.audit(payload(closed=True))["result"]["status"], "FAIL")

    def test_missing_market_field_fails(self):
        document = json.loads(payload())
        del document["events"][0]["markets"][0]["conditionId"]
        self.assertEqual(self.audit(json.dumps(document).encode())["result"]["status"], "FAIL")

    def test_duplicate_ids_fail(self):
        document = json.loads(payload())
        document["events"].append(document["events"][0].copy())
        self.assertEqual(self.audit(json.dumps(document).encode())["result"]["status"], "FAIL")

    def test_commit_is_required(self):
        with self.assertRaises(ContractError):
            audit_public_event_payload(payload(), self.spec, "2026-09-03T12:00:00Z", "Thu, 03 Sep 2026 12:00:01 GMT", "not-a-hash")

    def test_missing_server_date_quarantines_capture(self):
        record = audit_public_event_payload(payload(), self.spec, "2026-09-03T12:00:00Z", None, "abcdef1")
        self.assertEqual(record["result"]["status"], "FAIL")
        self.assertEqual(record["decision"], "quarantine_snapshot")


if __name__ == "__main__":
    unittest.main()
