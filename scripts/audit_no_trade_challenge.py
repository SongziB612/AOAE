"""Reconcile all challenger fills with the independent ledger, not its engine."""
import argparse
import csv
import json
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from hashlib import sha256
from pathlib import Path

from aoae.independent_cash_ledger import verify_ledger


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--result', type=Path, default=Path('research/experiments/cn-no-trade-0001/result-v1.json'))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.output.exists() or not args.output.resolve().is_relative_to(root):
        raise ValueError('new workspace output required')
    path = (root / args.result).resolve()
    if not path.is_relative_to(root):
        raise ValueError('workspace result required')
    result = json.loads(path.read_text())
    old = json.loads((root / result['config']['reference']).read_text())
    config = old['config']
    actions = json.loads((root / config['reference']).read_text())['inferred_actions']
    symbols = json.loads((root / config['strategy_spec']).read_text())['data']['risk_assets']
    prices = {}
    for symbol in symbols:
        with (root / config['data_dir'] / (symbol + '.csv')).open() as stream:
            for row in csv.DictReader(stream):
                prices.setdefault(row['date'], {})[symbol] = row['close']
    checks = []
    for run in result['runs']:
        rate = Decimal(str(config['commission_scenarios'][run['fee_scenario']]))
        slip = Decimal(str(run['slippage_bps'])) / 10000
        ledger = verify_ledger(run['dates'], prices, run['trades'], actions,
                               config['initial_cny'], rate, run['slippage_bps'])
        holdings = dict.fromkeys(symbols, 0)
        for day in run['dates']:
            for action in actions:
                if action['date'] == day and action['symbol'] in holdings:
                    symbol = action['symbol']
                    rounding = {'floor': ROUND_FLOOR, 'ceil': ROUND_CEILING}[action['rounding']]
                    holdings[symbol] = int((Decimal(holdings[symbol]) * Decimal(str(action['ratio']))).to_integral_value(rounding=rounding))
            for trade in run['trades']:
                if trade['date'] == day:
                    holdings[trade['symbol']] += trade['quantity'] * (1 if trade['side'] == 'BUY' else -1)
        exit_cost = Decimal(0)
        for symbol, quantity in holdings.items():
            if quantity:
                notional = quantity * Decimal(prices[day][symbol])
                exit_cost += max(Decimal(5), notional * rate) + notional * slip
        ledger[-1] -= float(exit_cost)
        error = max(abs(a - b) for a, b in zip(ledger, run['net_equity_cny'], strict=True))
        total_cost = sum((Decimal(t['cost']) for t in run['trades']), Decimal(0)) + exit_cost
        if error > .000001 or abs(float(total_cost) - run['total_cost_with_exit_cny']) > .000001:
            raise ValueError('independent cash/cost mismatch')
        if abs(ledger[-1] - config['initial_cny'] - run['net_pnl_cny']) > .0051:
            raise ValueError('terminal profit mismatch')
        checks.append({k: run[k] for k in ('year', 'fee_scenario', 'slippage_bps', 'band')} |
                      {'max_nav_error_cny': error, 'status': 'PASS'})
    audit = {'status': 'PASS', 'paths_checked': len(checks), 'checks': checks,
             'scope': 'Independent fee, funded cash, position, corporate-action, daily NAV and terminal exit-cost reconciliation; not independent signal validation or real fills.',
             'result_sha256': sha256(path.read_bytes()).hexdigest(),
             'auditor_sha256': sha256(Path(__file__).read_bytes()).hexdigest()}
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(audit, stream, indent=2, allow_nan=False)
    print('PASS', len(checks), 'independent ledger paths')


if __name__ == '__main__':
    main()
