"""Same-market cost/risk control: descriptive history, never fund approval."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

import pandas as pd

from aoae.corporate_action_replay import Action, replay, total_return_signals
from aoae.equal_vol_control import equal_vol_weights
from aoae.etf_momentum import load_spec, load_prices
from aoae.etf_risk_overlay import build_overlay_schedule
from aoae.independent_cash_ledger import verify_ledger


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    c = json.loads(args.config.read_text(encoding='utf-8'))
    if c['capital_authorized'] is not False or c['orders_authorized'] is not False:
        raise ValueError('research only')
    reference = json.loads(Path(c['reference']).read_text(encoding='utf-8'))
    spec = load_spec(Path(c['strategy_spec']))
    opens, closes, hashes = load_prices(Path(c['data_dir']), spec.symbols)
    execution_field = c.get('execution_price_field', 'open')
    if execution_field not in ('open', 'close'):
        raise ValueError('unsupported execution price field')
    # Close prices are used only as ex-post fills in this stress scenario.
    # Signal generation and previous-close lot sizing remain unchanged.
    execution_prices = closes.copy() if execution_field == 'close' else opens
    if hashes != reference['price_sha256']:
        raise ValueError('prices changed')
    actions = [Action(**{**a, 'date': pd.Timestamp(a['date']),
        'payment_date': pd.Timestamp(a['payment_date']) if a['payment_date'] else None}) for a in reference['inferred_actions']]
    index = total_return_signals(closes, actions)
    momentum = build_overlay_schedule(index, spec, c['lookback'], c['target_volatility'])
    equal, controlled = {}, {}
    for day, (_, scores, signal, diagnostics) in momentum.items():
        equal[day] = ({s: 1 / len(spec.risk_assets) for s in spec.risk_assets}, {}, signal, {})
        position = index.index.get_loc(pd.Timestamp(signal))
        controlled[day] = (equal_vol_weights(index, position, spec.risk_assets, c['lookback'], c['target_volatility']), {}, signal, {})
    schedules = {'existing_momentum': momentum, 'equal_monthly': equal, 'equal_vol_target': controlled}
    rows = []
    for year in c['years']:
        start, end = f'{year}-01-01', f'{year}-12-31'
        first = next(day for day in closes.index if day >= pd.Timestamp(start))
        previous = closes.index[closes.index.get_loc(first) - 1]
        schedules['equal_buy_hold'] = {first: ({s: 1 / len(spec.risk_assets) for s in spec.risk_assets}, {}, str(previous.date()), {})}
        for fee_name, rate in c['commission_scenarios'].items():
            for slip in c['slippage_bps']:
                for arm in c['arms']:
                    eq, orders, state = replay(execution_prices, closes, schedules[arm], actions, spec.risk_assets,
                        start, end, initial=c['initial_cny'], commission=rate, slippage_bps=slip,
                        pause_loss=c['pause_loss_cny'], use_payment_dates=True)
                    dates = [str(d.date()) for d in eq.index]
                    marks = {str(d.date()): {s: float(closes.at[d, s]) for s in spec.risk_assets} for d in eq.index}
                    independently = verify_ledger(dates, marks, orders, reference['inferred_actions'], c['initial_cny'], rate, slip)
                    error = max(abs(a - b) for a, b in zip(eq, independently, strict=True))
                    if error > .00001:
                        raise ValueError('independent accounting mismatch')
                    exit_fee = sum(max(5., q * float(closes.at[eq.index[-1], s]) * rate) + q * float(closes.at[eq.index[-1], s]) * slip / 10000 for s, q in state['ending_positions'].items() if q)
                    rows.append({'year': year, 'fee_scenario': fee_name, 'slippage_bps': slip, 'arm': arm,
                        'net_pnl_after_exit_haircut_cny': round(float(eq.iloc[-1]) - c['initial_cny'] - exit_fee, 2),
                        'max_drawdown_before_exit_haircut': float((eq / eq.cummax().clip(lower=c['initial_cny']) - 1).min()),
                        'orders': orders, 'equity_cny': eq.tolist(), 'dates': dates,
                        'state': state, 'independent_ledger_max_error': error})
        print('completed_year=' + str(year), flush=True)
    comparisons = []
    for fee in c['commission_scenarios']:
        for slip in c['slippage_bps']:
            for comparator in c['arms'][1:]:
                differences = []
                dd_changes = []
                for year in c['years']:
                    group = {r['arm']: r for r in rows if r['year'] == year and r['fee_scenario'] == fee and r['slippage_bps'] == slip}
                    differences.append(group['existing_momentum']['net_pnl_after_exit_haircut_cny'] - group[comparator]['net_pnl_after_exit_haircut_cny'])
                    dd_changes.append(group['existing_momentum']['max_drawdown_before_exit_haircut'] - group[comparator]['max_drawdown_before_exit_haircut'])
                comparisons.append({'fee_scenario': fee, 'slippage_bps': slip, 'comparator': comparator,
                    'annual_paired_pnl_advantage_cny': [round(x, 2) for x in differences],
                    'median_paired_pnl_advantage_cny': float(pd.Series(differences).median()),
                    'years_more_profit': sum(x > .01 for x in differences),
                    'years_less_severe_drawdown': sum(x > 1e-9 for x in dd_changes)})
    files = [str(args.config), c['reference'], c['strategy_spec'], 'scripts/audit_cn_momentum_value.py',
        'src/aoae/equal_vol_control.py', 'src/aoae/corporate_action_replay.py', 'src/aoae/independent_cash_ledger.py',
        'src/aoae/etf_momentum.py', 'src/aoae/etf_risk_overlay.py', 'src/aoae/small_account.py']
    result = {'experiment_id': c['experiment_id'], 'config': c, 'verdict': 'RESEARCH',
        'status': 'REUSED_HISTORICAL_RISK_CONTROL_COMPARISON', 'comparisons': comparisons, 'runs': rows,
        'price_sha256': hashes, 'input_sha256': {p: sha256(Path(p).read_bytes()).hexdigest() for p in files},
        'clean_oos_observations': 0, 'capital_authorized': False, 'orders_authorized': False,
        'limits': ['Four reused nonoverlapping years are not independent trials or clean OOS.',
            'Equal-vol control has its own causal equal-basket covariance, not champion exposure or realized-vol matching.',
            'All existing raw-price action/calendar/fill/settlement assumptions remain; fees are scenarios.',
            'Vol targeting is an estimate, not guaranteed realized risk or loss limit. Ruin probability unknown.',
            'Terminal exit is a mark-based cost haircut, not observed liquidation; drawdowns precede haircut.',
            'No parameter search, forecast model, new live/paper account or capital authorization.']}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(comparisons, indent=2))


if __name__ == '__main__':
    main()
