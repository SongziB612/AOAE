from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from aoae.paper_account import initialize_account, load_paper_spec, validate_order_draft


SPEC = Path("research/paper_accounts/0001-small-etf-risk-overlay/spec.json")


class PaperAccountTests(unittest.TestCase):
    def test_initial_state_has_cash_and_no_positions_or_authority(self):
        state = initialize_account(SPEC)
        self.assertEqual(state["cash_cny"], 10000)
        self.assertEqual(state["positions"], {})
        self.assertFalse(state["orders_authorized"])
        self.assertFalse(state["capital_authorized"])
        self.assertFalse(state["broker_connection_authorized"])

    def test_stale_signal_is_rejected(self):
        spec = load_paper_spec(SPEC)
        with self.assertRaisesRegex(ValueError, "stale"):
            validate_order_draft(spec, "2026-08-31", "2026-09-01", [{"quantity": 100, "price": 3.0}])

    def test_fractional_lot_is_rejected(self):
        spec = load_paper_spec(SPEC)
        with self.assertRaisesRegex(ValueError, "lot"):
            validate_order_draft(spec, "2026-09-30", "2026-10-08", [{"quantity": 50, "price": 3.0}])

    def test_risk_cap_is_enforced(self):
        spec = load_paper_spec(SPEC)
        with self.assertRaisesRegex(ValueError, "cap"):
            validate_order_draft(spec, "2026-09-30", "2026-10-08", [{"quantity": 1400, "price": 3.0}])

    def test_valid_integer_lot_draft_includes_minimum_cost(self):
        spec = load_paper_spec(SPEC)
        result = validate_order_draft(spec, "2026-09-30", "2026-10-08", [{"quantity": 100, "price": 3.0}])
        self.assertEqual(result, {"total_notional_cny": 300.0, "estimated_cost_cny": 5.0})
