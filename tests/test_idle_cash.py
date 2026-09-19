import unittest

from aoae.idle_cash import assess_idle_cash_candidate, reverse_repo_economics


class IdleCashTests(unittest.TestCase):
    def test_one_day_reverse_repo_economics(self):
        result = reverse_repo_economics(
            notional_cny=10000,
            annual_rate_percent=.875,
            actual_occupancy_days=1,
            commission_rate=.00001,
            minimum_commission_cny=.01,
        )
        self.assertAlmostEqual(result["gross_interest_cny"], .2397260274)
        self.assertAlmostEqual(result["commission_cny"], .1)
        self.assertAlmostEqual(result["net_income_cny"], .1397260274)
        self.assertAlmostEqual(result["break_even_annual_rate_percent"], .365)

    def test_unknown_operational_facts_fail_closed(self):
        economics = reverse_repo_economics(
            notional_cny=10000,
            annual_rate_percent=2,
            actual_occupancy_days=1,
            commission_rate=.00001,
            minimum_commission_cny=.01,
        )
        result = assess_idle_cash_candidate(
            economics,
            written_fee_schedule_confirmed=False,
            product_eligibility_confirmed=False,
            settlement_preserves_next_rebalance=False,
            executable_quote_confirmed=True,
        )
        self.assertFalse(result["admitted"])
        self.assertFalse(result["capital_authorized"])
        self.assertIn("written_fee_schedule_confirmed", result["failed_checks"])

    def test_nonpositive_net_income_is_rejected(self):
        economics = reverse_repo_economics(
            notional_cny=1000,
            annual_rate_percent=.1,
            actual_occupancy_days=1,
            commission_rate=.00001,
            minimum_commission_cny=.01,
        )
        result = assess_idle_cash_candidate(
            economics,
            written_fee_schedule_confirmed=True,
            product_eligibility_confirmed=True,
            settlement_preserves_next_rebalance=True,
            executable_quote_confirmed=True,
        )
        self.assertFalse(result["admitted"])
        self.assertIn("positive_net_income_after_fees", result["failed_checks"])

    def test_invalid_notional_is_rejected(self):
        with self.assertRaises(ValueError):
            reverse_repo_economics(
                notional_cny=0,
                annual_rate_percent=1,
                actual_occupancy_days=1,
                commission_rate=0,
                minimum_commission_cny=0,
            )


if __name__ == "__main__":
    unittest.main()
