from pathlib import Path
import unittest

import numpy as np
import pandas as pd

from aoae.etf_momentum import MomentumSpec
from aoae.paper_account import initialize_account, load_paper_spec, validate_order_draft
from aoae.paper_daily import roll_forward


SPEC = Path("research/paper_accounts/0004-3000-live-pilot-shadow/spec.json")


class PilotAccountTests(unittest.TestCase):
    def test_exact_pilot_scale_and_risk_pause(self):
        spec = load_paper_spec(SPEC)
        state = initialize_account(SPEC)
        self.assertEqual(state["cash_cny"], 3000)
        self.assertEqual(state["risk_budget"]["pause_new_risk_at_loss_cny"], 600)
        self.assertEqual(spec["cost_model"]["one_way_rate"], .003)
        self.assertFalse(state["capital_authorized"])

    def test_order_draft_reserves_maximum_fee(self):
        spec = load_paper_spec(SPEC)
        result = validate_order_draft(spec, "2026-09-30", "2026-10-08", [{"quantity": 800, "price": 3.0}])
        self.assertEqual(result, {"total_notional_cny": 2400.0, "estimated_cost_cny": 7.2})
        with self.assertRaisesRegex(ValueError, "available starting cash"):
            validate_order_draft(spec, "2026-09-30", "2026-10-08", [{"quantity": 1000, "price": 3.0}])

    def test_exact_pilot_pause_and_next_open_liquidation(self):
        account = load_paper_spec(SPEC)
        strategy = MomentumSpec(
            symbols=("A", "B", "D"), risk_assets=("A", "B"), defensive_asset="D", benchmark="A",
            windows=(126, 252), skip=21, top_n=2, cost_rate=.003, initial_capital=3000,
            holdout_start="2022-01-01", holdout_end="2026-08-31",
        )
        index = pd.bdate_range("2025-06-02", "2026-10-01")
        close = pd.DataFrame({"A": np.full(len(index), 3.0), "B": np.full(len(index), 4.0), "D": np.full(len(index), 100.0)}, index=index)
        state = initialize_account(SPEC)
        state.update({
            "as_of": "2026-09-29", "cash_cny": 2000.0,
            "positions": {"A": {"quantity": 100, "market_value_cny": 300.0}}, "events": [],
        })
        result = roll_forward(state, account, strategy, close, close, "2026-10-01")
        self.assertEqual(result["status"], "PAUSED_AFTER_RISK_LIMIT")
        self.assertEqual(result["positions"], {})
        self.assertEqual([event["type"] for event in result["events"]], ["RISK_PAUSE_TRIGGERED_AT_CLOSE", "PAPER_RISK_LIQUIDATION"])


if __name__ == "__main__":
    unittest.main()
