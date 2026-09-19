"""Evaluate an observed quote under explicit, non-evidentiary fee/day scenarios."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from aoae.experiment import write_record
from aoae.idle_cash import assess_idle_cash_candidate, reverse_repo_economics


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("spec", type=Path)
    parser.add_argument("quote", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    quote = json.loads(args.quote.read_text(encoding="utf-8"))
    annual_rate = float(quote["quotes"]["GC001"]["最新价"])
    scenarios = []
    for notional in (3000.0, 10000.0):
        for days in (1, 3):
            economics = reverse_repo_economics(
                notional_cny=notional,
                annual_rate_percent=annual_rate,
                actual_occupancy_days=days,
                commission_rate=.00001,
                minimum_commission_cny=.01,
            )
            scenarios.append({
                **economics,
                "scenario_inputs": {
                    "commission_rate_from_huatai_public_schedule": .00001,
                    "minimum_commission_cny_from_user_account_schedule": .01,
                    "actual_occupancy_days": days,
                },
            })

    representative = scenarios[2]
    assessment = assess_idle_cash_candidate(
        representative,
        written_fee_schedule_confirmed=True,
        product_eligibility_confirmed=False,
        settlement_preserves_next_rebalance=False,
        executable_quote_confirmed=False,
    )
    record = {
        "schema_version": 1,
        "record_type": "idle_cash_reverse_repo_screen",
        "evidence": {
            "spec_path": str(args.spec),
            "spec_sha256": _sha256(args.spec),
            "quote_path": str(args.quote),
            "quote_sha256": _sha256(args.quote),
            "observed_gc001_annual_rate_percent": annual_rate,
            "huatai_fee_schedule_url": "https://www.htsc.com.cn/browser/tjjd/investment.do",
            "user_fee_schedule_evidence": "conversation screenshot: general pledge repo minimum commission CNY 0.01",
        },
        "scenarios": scenarios,
        "assessment": assessment,
        "decision": "BLOCKED_INPUTS" if not assessment["admitted"] else "ADMIT",
        "interpretation": (
            "The public quote makes the hypothetical economics measurable, but it is not an executable "
            "broker quote. Written commission, eligibility, and settlement behavior remain unconfirmed."
        ),
        "orders_placed": 0,
        "capital_authorized": False,
    }
    digest = write_record(args.output, record)
    print(f"wrote {args.output} sha256={digest}")


if __name__ == "__main__":
    main()
