"""Replay all existing CN-VALUE paths with the new Decimal daily engine.

Reused historical data, not a new holdout or forward-profit claim. No tuning.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path

import pandas as pd

from aoae.corporate_action_replay import Action, total_return_signals
from aoae.equal_vol_control import equal_vol_weights
from aoae.etf_momentum import load_prices, load_spec
from aoae.etf_risk_overlay import build_overlay_schedule
from aoae.shadow_accounting import advance_day, new_account, dec


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    source = Path('research/experiments/cn-value-0001/result-v1.json')
    old = json.loads(source.read_text(encoding='utf-8'))
    c = old['config']
    ref = json.loads(Path(c['reference']).read_text(encoding='utf-8'))
    spec = load_spec(Path(c['strategy_spec']))
    opens, closes, hashes = load_prices(Path(c['data_dir']), spec.symbols)
    if hashes != old['price_sha256'] or hashes != ref['price_sha256']:
        raise ValueError('historical input changed')
    actions = [Action(**{**a, 'date': pd.Timestamp(a['date']), 'payment_date': pd.Timestamp(a['payment_date']) if a['payment_date'] else None}) for a in ref['inferred_actions']]
    index = total_return_signals(closes, actions)
    momentum = build_overlay_schedule(index, spec, c['lookback'], c['target_volatility'])
    schedules = {'existing_momentum': {d: {s: w.get(s, 0) for s in spec.risk_assets} for d, (w, _, _, _) in momentum.items()},
                 'equal_monthly': {d: {s: 1 / len(spec.risk_assets) for s in spec.risk_assets} for d in momentum},
                 'equal_vol_target': {d: equal_vol_weights(index, index.index.get_loc(pd.Timestamp(signal)), spec.risk_assets, c['lookback'], c['target_volatility']) for d, (_, _, signal, _) in momentum.items()}}
    event_map = {}
    for n, a in enumerate(actions):
        if a.symbol in spec.risk_assets:
            event_map.setdefault(a.date, []).append({'id': str(n), 'symbol': a.symbol, 'date': str(a.date.date()),
                'ratio': a.ratio, 'cash_per_old_share': a.cash_per_old_share,
                'payment_date': str(a.payment_date.date()) if a.payment_date is not None else None, 'rounding': a.rounding})
    rows = []
    for run in old['runs']:
        account = new_account(c['initial_cny'], c['pause_loss_cny'])
        errors, fills = [], 0
        rate = c['commission_scenarios'][run['fee_scenario']]
        for date, expected in zip(run['dates'], run['equity_cny'], strict=True):
            day = pd.Timestamp(date)
            loc = closes.index.get_loc(day)
            if run['arm'] == 'equal_buy_hold':
                target = {s: 1 / len(spec.risk_assets) for s in spec.risk_assets} if date == run['dates'][0] else None
            else:
                target = schedules[run['arm']].get(day)
            account, trades = advance_day(account, date, str(closes.index[loc - 1].date()),
                opens.loc[day, list(spec.risk_assets)].to_dict(), closes.loc[day, list(spec.risk_assets)].to_dict(),
                closes.iloc[loc - 1][list(spec.risk_assets)].to_dict(), event_map.get(day, []), target,
                commission=rate, slippage_bps=run['slippage_bps'])
            errors.append(abs(float(account['equity']) - expected))
            fills += len(trades)
        exit_cost = sum((max(dec(5), q * dec(closes.at[day, s]) * dec(rate)) + q * dec(closes.at[day, s]) * dec(run['slippage_bps']) / 10000 for s, q in account['positions'].items() if q), dec(0))
        pnl = float(dec(account['equity']) - dec(c['initial_cny']) - exit_cost)
        rows.append({k: run[k] for k in ('year', 'arm', 'fee_scenario', 'slippage_bps')} | {
            'net_pnl_after_exit_haircut_cny': round(pnl, 2), 'return_on_initial': pnl / c['initial_cny'],
            'max_drawdown_before_exit': float(account['max_drawdown']), 'modeled_fills': fills,
            'max_daily_reference_error_cny': max(errors), 'pnl_reference_error_cny': abs(round(pnl, 2) - run['net_pnl_after_exit_haircut_cny']),
            'reference_fill_count_matches': fills == len(run['orders']), 'paused': account['paused']})
        print(f"{run['year']} {run['arm']} fee={rate} slip={run['slippage_bps']} pnl={pnl:.2f} error={max(errors):.9f}", flush=True)
    passed = all(r['max_daily_reference_error_cny'] < .01 and r['pnl_reference_error_cny'] < .011 and r['reference_fill_count_matches'] for r in rows)
    result = {'experiment_id': 'CN-SHADOW-REAL-REPLAY-0001', 'accounting_verification': 'PASS' if passed else 'FAIL',
        'runs': rows, 'reference_sha256': sha256(source.read_bytes()).hexdigest(), 'price_sha256': hashes,
        'source_sha256': {name: sha256(Path(name).read_bytes()).hexdigest() for name in
            ['scripts/verify_real_shadow_economics.py', 'src/aoae/shadow_accounting.py', c['reference'], c['strategy_spec']]},
        'clean_oos_observations': 0, 'capital_authorized': False, 'orders_authorized': False,
        'limits': ['Reused four historical years; no new independent profitability evidence.',
                   'Shared signal generation, separately implemented daily accounting.',
                   'Provider actions and modeled open fills retain prior evidence limitations.',
                   'Costs are scenarios, not confirmed personal commission. Terminal exit is a haircut, not a fill.']}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as f:
        json.dump(result, f, indent=2, allow_nan=False)
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
