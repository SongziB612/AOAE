from __future__ import annotations

import argparse
import json
from pathlib import Path

from aoae.etf_momentum import load_spec
from aoae.paper_account import load_paper_spec
from aoae.paper_daily import load_extended_panels, roll_forward


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--account-spec", type=Path, required=True)
    parser.add_argument("--strategy-spec", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--frozen-data-dir", type=Path, required=True)
    parser.add_argument("--update-data-dir", type=Path, required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite paper snapshot: {args.output}")
    account_spec = load_paper_spec(args.account_spec)
    strategy_spec = load_spec(args.strategy_spec)
    state = json.loads(args.state.read_text(encoding="utf-8"))
    open_price, close = load_extended_panels(args.frozen_data_dir, args.update_data_dir, strategy_spec.symbols)
    result = roll_forward(state, account_spec, strategy_spec, open_price, close, args.as_of)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("as_of", "status", "cash_cny", "positions", "equity_cny", "risk_budget", "last_run")}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
