"""Fail-closed economics for idle-cash reverse-repurchase candidates."""

from __future__ import annotations

from typing import Any


def reverse_repo_economics(
    *,
    notional_cny: float,
    annual_rate_percent: float,
    actual_occupancy_days: int,
    commission_rate: float,
    minimum_commission_cny: float,
) -> dict[str, float]:
    """Calculate gross interest, commission, net income, and break-even yield."""
    if notional_cny <= 0:
        raise ValueError("notional must be positive")
    if annual_rate_percent < 0:
        raise ValueError("annual rate cannot be negative")
    if actual_occupancy_days <= 0:
        raise ValueError("actual occupancy days must be positive")
    if commission_rate < 0 or minimum_commission_cny < 0:
        raise ValueError("commission inputs cannot be negative")

    commission = max(notional_cny * commission_rate, minimum_commission_cny)
    gross_interest = (
        notional_cny
        * (annual_rate_percent / 100.0)
        * actual_occupancy_days
        / 365.0
    )
    net_income = gross_interest - commission
    break_even_annual_rate_percent = (
        commission
        / notional_cny
        * 365.0
        / actual_occupancy_days
        * 100.0
    )
    return {
        "notional_cny": notional_cny,
        "annual_rate_percent": annual_rate_percent,
        "actual_occupancy_days": actual_occupancy_days,
        "gross_interest_cny": gross_interest,
        "commission_cny": commission,
        "net_income_cny": net_income,
        "break_even_annual_rate_percent": break_even_annual_rate_percent,
    }


def assess_idle_cash_candidate(
    economics: dict[str, float],
    *,
    written_fee_schedule_confirmed: bool,
    product_eligibility_confirmed: bool,
    settlement_preserves_next_rebalance: bool,
    executable_quote_confirmed: bool,
) -> dict[str, Any]:
    """Admit a cash product only when economics and operational facts are known."""
    checks = {
        "positive_net_income_after_fees": economics["net_income_cny"] > 0,
        "written_fee_schedule_confirmed": written_fee_schedule_confirmed is True,
        "product_eligibility_confirmed": product_eligibility_confirmed is True,
        "settlement_preserves_next_rebalance": settlement_preserves_next_rebalance is True,
        "executable_quote_confirmed": executable_quote_confirmed is True,
    }
    admitted = all(checks.values())
    return {
        "checks": checks,
        "failed_checks": [name for name, passed in checks.items() if not passed],
        "admitted": admitted,
        "capital_authorized": False,
    }
