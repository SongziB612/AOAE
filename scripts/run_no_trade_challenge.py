"""Real-data historical challenger, all costs/years/bands retained, no live writes."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import numpy as np
import pandas as pd
from aoae.corporate_action_replay import Action, total_return_signals
from aoae.etf_momentum import load_prices, load_spec
from aoae.etf_risk_overlay import build_overlay_schedule
from aoae.no_trade_band import filter_target
from aoae.research_freeze import verify_freeze
from aoae.shadow_accounting import advance_day, new_account, dec


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--spec', type=Path, default=Path('research/experiments/cn-no-trade-0001/spec.json'))
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.output.exists() or not args.output.resolve().is_relative_to(root):
        raise ValueError('new workspace output required')
    spec_path = (root / args.spec).resolve()
    if not spec_path.is_relative_to(root):
        raise ValueError('workspace specification required')
    contract = json.loads(spec_path.read_text())
    old = json.loads((root / contract['reference']).read_text())
    c = old['config']
    freeze = json.loads((root / 'research/prospective/0003-raw-price-300k-paired-forward/freeze.json').read_text())
    if verify_freeze(root, freeze)['status'] != 'INTACT':
        raise ValueError('freeze changed')
    spec = load_spec(root / c['strategy_spec'])
    opens, closes, hashes = load_prices(root / c['data_dir'], spec.symbols)
    if hashes != old['price_sha256']:
        raise ValueError('prices changed')
    ref = json.loads((root / c['reference']).read_text())
    actions = [Action(**{**a, 'date': pd.Timestamp(a['date']), 'payment_date': pd.Timestamp(a['payment_date']) if a['payment_date'] else None}) for a in ref['inferred_actions']]
    index = total_return_signals(closes, actions)
    schedule = build_overlay_schedule(index, spec, c['lookback'], c['target_volatility'])
    events = {}
    for i, a in enumerate(actions):
        if a.symbol in spec.risk_assets:
            events.setdefault(str(a.date.date()), []).append({'id': str(i), 'symbol': a.symbol, 'date': str(a.date.date()),
                'ratio': a.ratio, 'cash_per_old_share': a.cash_per_old_share,
                'payment_date': str(a.payment_date.date()) if a.payment_date is not None else None, 'rounding': a.rounding})
    rows = []
    for run in old['runs']:
        if run['arm'] != 'existing_momentum':
            continue
        rate = c['commission_scenarios'][run['fee_scenario']]
        for band in contract['bands']:
            account = new_account(c['initial_cny'], c['pause_loss_cny'])
            previous_target, nav, decisions, trades, exposure = None, [], Counter(), [], []
            for day in run['dates']:
                stamp = pd.Timestamp(day)
                loc = closes.index.get_loc(stamp)
                previous = closes.index[loc - 1]
                prior = closes.iloc[loc - 1][list(spec.risk_assets)].to_dict()
                target = {s: schedule[stamp][0].get(s, 0) for s in spec.risk_assets} if stamp in schedule else None
                if target is not None and pd.Timestamp(schedule[stamp][2]) > previous:
                    raise ValueError('future signal')
                submitted, reason = filter_target(account, target, previous_target, prior, band)
                decisions[reason] += 1
                if target is not None:
                    previous_target = target
                account, fills = advance_day(account, day, str(previous.date()),
                    opens.loc[stamp, list(spec.risk_assets)].to_dict(), closes.loc[stamp, list(spec.risk_assets)].to_dict(),
                    prior, events.get(day, []), submitted, commission=rate, slippage_bps=run['slippage_bps'])
                nav.append(float(account['equity']))
                trades.extend(fills)
                exposure.append(float(sum(dec(q) * dec(closes.at[stamp, s]) for s, q in account['positions'].items()) / dec(account['equity'])))
            exit_cost = sum((max(dec(5), q * dec(closes.at[stamp, s]) * dec(rate)) + q * dec(closes.at[stamp, s]) * dec(run['slippage_bps']) / 10000 for s, q in account['positions'].items() if q), dec(0))
            terminal = dec(account['equity']) - exit_cost
            pnl = round(float(terminal - dec(c['initial_cny'])), 2)
            if band == 0 and (max(abs(a-b) for a,b in zip(nav,run['equity_cny'],strict=True)) > .01 or abs(pnl-run['net_pnl_after_exit_haircut_cny']) > .011 or len(trades) != len(run['orders'])):
                raise ValueError('zero-band accounting does not reproduce historical reference')
            net_nav = np.array(nav)
            net_nav[-1] = float(terminal)
            returns = net_nav / np.r_[c['initial_cny'], net_nav[:-1]] - 1
            rows.append({k: run[k] for k in ('year','fee_scenario','slippage_bps')} | {
                'band': band, 'net_pnl_cny': pnl, 'net_return': float(terminal/dec(c['initial_cny'])-1),
                'log_growth': float(np.log(float(terminal)/c['initial_cny'])),
                'net_sharpe_zero_cash': float(returns.mean()/returns.std(ddof=1)*np.sqrt(252)),
                'max_drawdown': float(account['max_drawdown']), 'total_cost_with_exit_cny': float(dec(account['cost'])+exit_cost),
                'average_gross_exposure': float(np.mean(exposure)),
                'turnover_initial_capital': float(sum(dec(t['quantity'])*dec(t['price']) for t in trades)/dec(c['initial_cny'])),
                'modeled_fills': len(trades), 'decision_counts': dict(decisions), 'dates':run['dates'], 'net_equity_cny':net_nav.tolist(),
                'trades':trades, 'paused':account['paused'], 'independent_market_samples':None, 'risk_of_ruin':None})
        print('completed', run['year'], run['fee_scenario'], run['slippage_bps'], flush=True)
    comparisons = []
    for row in rows:
        base = next(r for r in rows if r['band']==0 and all(r[k]==row[k] for k in ('year','fee_scenario','slippage_bps')))
        comparisons.append({k:row[k] for k in ('year','fee_scenario','slippage_bps','band')} | {
            'incremental_net_pnl_cny':round(row['net_pnl_cny']-base['net_pnl_cny'],2),
            'cost_saving_cny':round(base['total_cost_with_exit_cny']-row['total_cost_with_exit_cny'],2),
            'drawdown_change':row['max_drawdown']-base['max_drawdown']})
    primary = [r for r in comparisons if r['band']==contract['primary_band']]
    survives = all(sum(r['incremental_net_pnl_cny']>.01 for r in primary if r['fee_scenario']==f and r['slippage_bps']==s)>=3 for f in c['commission_scenarios'] for s in c['slippage_bps']) and all(r['drawdown_change']>=-.01 for r in primary)
    result = {'experiment_id':contract['experiment_id'], 'verdict':'RESEARCH' if survives else 'REJECT',
        'primary_meets_descriptive_screen':survives, 'runs':rows, 'comparisons':comparisons,
        'config':contract, 'baseline_accounting_check':'PASS_ALL_CONTROL_PATHS',
        'baseline_control_paths':sum(row['band']==0 for row in rows), 'clean_oos_observations':0,
        'capital_authorized':False, 'orders_authorized':False,
        'limits':['No-trade heuristic inspired by literature, not theorem or external package reproduction.',
                  'Four reused years are not independent prospective trials; no promotion or band optimization.',
                  'Gross exposure drift can change beta; cost savings alone do not prove alpha.',
                  'Raw actions, modeled open fills, fee scenarios and liquidity limitations inherited.'],
        'source_sha256':{str(f.relative_to(root)):sha256(f.read_bytes()).hexdigest() for f in [spec_path,root/contract['reference'],root/c['reference'],Path(__file__).resolve(),root/'src/aoae/no_trade_band.py',root/'src/aoae/shadow_accounting.py']},
        'price_sha256':hashes}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2,allow_nan=False)
    print('VERDICT',result['verdict'])


if __name__=='__main__':
    main()
