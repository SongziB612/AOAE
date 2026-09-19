from __future__ import annotations

import unittest
from copy import deepcopy

import numpy as np
import pandas as pd

from aoae.etf_momentum import MomentumSpec
from aoae.paper_account import load_paper_spec
from aoae.paper_daily import roll_forward


class PaperDailyTests(unittest.TestCase):
    def setUp(self):
        self.account = load_paper_spec(__import__("pathlib").Path("research/paper_accounts/0001-small-etf-risk-overlay/spec.json"))
        self.strategy = MomentumSpec(
            symbols=("A", "B", "D"), risk_assets=("A", "B"), defensive_asset="D", benchmark="A",
            windows=(126, 252), skip=21, top_n=2, cost_rate=0.0015, initial_capital=100000,
            holdout_start="2022-01-01", holdout_end="2026-08-31",
        )
        index = pd.bdate_range("2025-06-02", "2026-10-01")
        self.close = pd.DataFrame({"A": np.linspace(2, 4, len(index)), "B": np.linspace(3, 5, len(index)), "D": np.linspace(100, 101, len(index))}, index=index)
        self.open = self.close.copy()
        self.state = {"as_of": "2026-09-30", "status": "ACTIVE_WAITING_FOR_FIRST_ELIGIBLE_SIGNAL", "cash_cny": 10000.0, "positions": {}, "events": [], "orders_authorized": False, "capital_authorized": False, "broker_connection_authorized": False}

    def test_first_day_of_new_month_creates_integer_lot_paper_rebalance(self):
        result = roll_forward(self.state, self.account, self.strategy, self.open, self.close, "2026-10-01")
        self.assertEqual(result["last_run"]["generated_rebalances"], 1)
        self.assertTrue(all(item["quantity"] % 100 == 0 for item in result["positions"].values()))
        self.assertLessEqual(result["market_value_cny"], 4000.01)
        self.assertFalse(result["orders_authorized"])

    def test_same_as_of_is_idempotent(self):
        result = roll_forward(self.state, self.account, self.strategy, self.open, self.close, "2026-09-30")
        self.assertEqual(result["last_run"], {"requested_as_of": "2026-09-30", "processed_market_days": 0, "generated_rebalances": 0})
        self.assertEqual(result["events"], [])

    def test_daily_challenger_rebalances_without_waiting_for_month_end(self):
        account = deepcopy(self.account)
        account["execution"]["signal"] = "every_common_trading_day_close"
        account["execution"]["maximum_risk_asset_market_value_fraction"] = 1.0
        account["execution"]["target_annualized_volatility"] = 0.054
        state = dict(self.state)
        state.update({"as_of": "2026-09-29", "events": []})
        result = roll_forward(state, account, self.strategy, self.open, self.close, "2026-09-30")
        self.assertEqual(result["last_run"]["generated_rebalances"], 1)
        self.assertEqual(result["events"][0]["type"], "PAPER_DAILY_REBALANCE")

    def test_account_cannot_roll_backward(self):
        with self.assertRaisesRegex(ValueError, "backward"):
            roll_forward(self.state, self.account, self.strategy, self.open, self.close, "2026-09-29")

    def test_risk_pause_liquidates_at_following_open(self):
        state = dict(self.state)
        state.update({
            "as_of": "2026-09-29", "cash_cny": 5000.0,
            "positions": {"A": {"quantity": 100, "market_value_cny": 400.0}}, "events": [],
        })
        result = roll_forward(state, self.account, self.strategy, self.open, self.close, "2026-10-01")
        self.assertEqual(result["status"], "PAUSED_AFTER_RISK_LIMIT")
        self.assertEqual(result["positions"], {})
        self.assertEqual([event["type"] for event in result["events"]], ["RISK_PAUSE_TRIGGERED_AT_CLOSE", "PAPER_RISK_LIQUIDATION"])
