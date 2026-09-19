"""Fixed same-universe comparison; existing raw replay plus independent ledger."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

import pandas as pd

from aoae.cn_universal import monthly_schedules, simplex_lattice
from aoae.corporate_action_replay import Action, replay, total_return_signals
from aoae.etf_momentum import load_prices
from aoae.independent_cash_ledger import verify_ledger


def experiment(config):
    for flag in ('capital_authorized', 'orders_authorized', 'broker_connection_authorized'):
        if config.get(flag) is not False:
            raise ValueError('research only')
    reference = json.loads(Path(config['reference']).read_text(encoding='utf-8'))
    assets = tuple(config['assets'])
    # Preserve the SAME common calendar as the earlier six-ETF raw replay.
    opens, closes, hashes = load_prices(Path(config['data_dir']), tuple(reference['price_sha256']))
    if hashes != reference['price_sha256']:
        raise ValueError('raw price snapshot changed')
    actions = [Action(**{**a, 'date': pd.Timestamp(a['date']),
                        'payment_date': pd.Timestamp(a['payment_date']) if a['payment_date'] else None})
               for a in reference['inferred_actions']]
    signals = total_return_signals(closes, actions)
    rows = []
    for year in config['years']:
        start, end = f'{year}-01-01', f'{year}-12-31'
        schedules = monthly_schedules(signals, assets, start, end, config['grid_units'])
        for slip in config['slippage_bps']:
            for arm in config['arms']:
                eq, orders, state = replay(opens, closes, schedules[arm], actions, assets,
                    start, end, initial=config['initial_cny'], commission=config['commission_each_side'],
                    slippage_bps=slip, pause_loss=config['pause_loss_cny'], use_payment_dates=True)
                days = [str(d.date()) for d in eq.index]
                marks = {str(d.date()): {s: float(closes.at[d, s]) for s in assets} for d in eq.index}
                independently = verify_ledger(days, marks, orders, reference['inferred_actions'],
                    config['initial_cny'], config['commission_each_side'], slip)
                error = max(abs(a - b) for a, b in zip(eq, independently, strict=True))
                if error > .00001:
                    raise ValueError('independent ledger mismatch')
                exit_cost = sum(max(5., q * float(closes.at[eq.index[-1], s]) * config['commission_each_side'])
                                + q * float(closes.at[eq.index[-1], s]) * slip / 10000
                                for s, q in state['ending_positions'].items() if q)
                pnl = float(eq.iloc[-1]) - config['initial_cny'] - exit_cost
                rows.append({'year': year, 'slippage_bps': slip, 'arm': arm,
                    'net_pnl_after_exit_haircut_cny': round(pnl, 2),
                    'net_return_after_exit_haircut': pnl / config['initial_cny'],
                    'max_drawdown_before_exit_haircut': float((eq / eq.cummax().clip(lower=config['initial_cny']) - 1).min()),
                    'maximum_loss_from_initial_before_exit_haircut_cny': max(0., config['initial_cny'] - float(eq.min())),
                    'total_trading_cost_cny': state['cost_cny'], 'terminal_exit_cost_proxy_cny': exit_cost,
                    'order_count': len(orders), 'paused': state['paused'], 'independent_ledger_max_error': error,
                    'dates': days, 'equity_cny': eq.tolist(), 'orders': orders, 'ending_state': state})
        print('completed_year=' + str(year), flush=True)
    paired = []
    for year in config['years']:
        for slip in config['slippage_bps']:
            group = {r['arm']: r for r in rows if r['year'] == year and r['slippage_bps'] == slip}
            up = group['up_monthly']['net_pnl_after_exit_haircut_cny']
            paired.append({'year': year, 'slippage_bps': slip,
                'up_minus_equal_monthly_cny': round(up - group['equal_monthly']['net_pnl_after_exit_haircut_cny'], 2),
                'up_minus_equal_buy_hold_cny': round(up - group['equal_buy_hold']['net_pnl_after_exit_haircut_cny'], 2)})
    files = [config['reference'], 'src/aoae/cn_universal.py', 'src/aoae/corporate_action_replay.py',
             'src/aoae/independent_cash_ledger.py', 'src/aoae/etf_momentum.py', 'src/aoae/small_account.py',
             'scripts/run_cn_universal_comparison.py']
    return {'experiment_id': config['experiment_id'], 'verdict': 'RESEARCH',
        'status': 'DESCRIPTIVE_REUSED_HISTORICAL_EXECUTION_PROXY', 'config': config,
        'expert_count': len(simplex_lattice(len(assets), config['grid_units'])),
        'price_sha256': hashes, 'input_sha256': {p: sha256(Path(p).read_bytes()).hexdigest() for p in files},
        'runs': rows, 'paired_differences': paired, 'costed_runs': len(rows),
        'nonoverlapping_calendar_years': len(config['years']), 'independent_clean_oos_count': 0,
        'limits': ['Reused data and present-day selected universe, not clean OOS or probability estimates.',
            '70-point grid if five assets/four units: finite gross-scored monthly mixture, not exact Cover or net-optimal.',
            'Monthly expert marks ignore next-open timing difference; actual ledger includes configured costs.',
            'Corporate-action announcement PIT, exact fills, suspension/limit/queue and opening capacity not certified.',
            'Shared old CN engine retains intersection calendar and assumed executable raw open; no US settlement rules imported.',
            'Terminal cost is a mark-based haircut, not an executed liquidation. Drawdown is before this haircut.',
            'Configured commission is screenshot-based stress scenario, not personal account confirmation.',
            'Annual resets, paused forced liquidation and order sequencing are shared across arms. Risk of ruin unknown.'],
        'capital_authorized': False, 'orders_authorized': False, 'broker_connection_authorized': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    result = experiment(json.loads(args.config.read_text(encoding='utf-8')))
    result['config_sha256'] = sha256(args.config.read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    print(json.dumps(result['paired_differences'], indent=2))


if __name__ == '__main__':
    main()
