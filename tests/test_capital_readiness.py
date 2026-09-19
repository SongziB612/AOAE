import unittest

from aoae.capital_readiness import apply_derived_rule, assess_capital_readiness, evaluate_condition, resolve_json_path


def gate(identifier, status="PASS"):
    return {"id": identifier, "status": status, "evidence": ["evidence.json"]}


class CapitalReadinessTests(unittest.TestCase):
    def test_external_wait_does_not_hide_completed_internal_work(self):
        result = assess_capital_readiness([
            gate("strategy"),
            gate("forward", "PENDING_EXTERNAL_TIME"),
            gate("account", "PENDING_EXTERNAL_ACCOUNT"),
            gate("approval", "PENDING_USER_APPROVAL"),
        ])
        self.assertTrue(result["all_controllable_preparation_complete"])
        self.assertFalse(result["ready_for_capital"])
        self.assertFalse(result["capital_authorized"])

    def test_internal_pending_blocks_controllable_completion(self):
        result = assess_capital_readiness([gate("runbook", "PENDING_INTERNAL")])
        self.assertFalse(result["all_controllable_preparation_complete"])

    def test_failure_blocks_readiness(self):
        result = assess_capital_readiness([gate("model", "FAIL")])
        self.assertEqual(result["failed_gate_ids"], ["model"])
        self.assertFalse(result["ready_for_capital"])

    def test_missing_evidence_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "lacks evidence"):
            assess_capital_readiness([{"id": "x", "status": "PASS", "evidence": []}])

    def test_strict_json_assertion_path(self):
        self.assertEqual(resolve_json_path({"result": {"status": "PASS"}}, ["result", "status"]), "PASS")
        with self.assertRaisesRegex(ValueError, "missing assertion path"):
            resolve_json_path({"result": {}}, ["result", "status"])

    def test_derived_condition_operators(self):
        self.assertTrue(evaluate_condition(50, "gte", 50))
        self.assertTrue(evaluate_condition("ACTIVE", "in", ["ACTIVE", "WAITING"]))
        self.assertFalse(evaluate_condition(-.21, "gte", -.2))
        with self.assertRaisesRegex(ValueError, "unsupported"):
            evaluate_condition(1, "approximately", 1)

    def test_derived_gate_waits_then_passes_or_fails(self):
        source = "progress.json"
        gate_value = {
            "id": "forward", "status": "PENDING_EXTERNAL_TIME", "evidence": [source],
            "derived_rule": {
                "activate_when": [{"source": source, "path": ["review"], "operator": "equals", "value": True}],
                "pass_when": [{"source": source, "path": ["pnl"], "operator": "gt", "value": 0}],
            },
        }
        self.assertEqual(apply_derived_rule(gate_value, {source: {"review": False, "pnl": -1}})["status"], "PENDING_EXTERNAL_TIME")
        self.assertEqual(apply_derived_rule(gate_value, {source: {"review": True, "pnl": 1}})["status"], "PASS")
        self.assertEqual(apply_derived_rule(gate_value, {source: {"review": True, "pnl": 0}})["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
