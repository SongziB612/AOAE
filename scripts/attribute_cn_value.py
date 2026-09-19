"""Attribute all already-fixed CN-VALUE-0001 paths without new strategy trials."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import statistics

from aoae.asset_attribution import attribute
from aoae.etf_momentum import load_prices


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    source = json.loads(args.source.read_text(encoding='utf-8'))
    for name, expected in source['input_sha256'].items():
        if sha256(Path(name).read_bytes()).hexdigest() != expected:
            raise ValueError('changed source evidence: ' + name)
    c = source['config']
    reference = json.loads(Path(c['reference']).read_text(encoding='utf-8'))
    spec = json.loads(Path(c['strategy_spec']).read_text(encoding='utf-8'))
    assets = spec['data']['risk_assets']
    _, closes, hashes = load_prices(Path(c['data_dir']), tuple(source['price_sha256']))
    if hashes != source['price_sha256']:
        raise ValueError('changed price data')
    date_marks = {str(d.date()): {s: float(row[s]) for s in assets} for d, row in closes.iterrows()}
    rows, largest = [], 0.
    for run in source['runs']:
        rate = c['commission_scenarios'][run['fee_scenario']]
        marks = {d: date_marks[d] for d in run['dates']}
        result = attribute(run['dates'], marks, run['orders'], reference['inferred_actions'], c['initial_cny'], rate, run['slippage_bps'])
        error = max(abs(r['reconstructed_equity_cny'] - expected) for r, expected in zip(result['daily'], run['equity_cny'], strict=True))
        terminal_error = abs(result['net_pnl_after_exit_haircut_cny'] - run['net_pnl_after_exit_haircut_cny'])
        if error > .00001 or terminal_error > .00501:
            raise ValueError('attribution does not reconcile')
        largest = max(largest, error)
        rows.append({k: run[k] for k in ('year', 'fee_scenario', 'slippage_bps', 'arm')} | result)
    paired = []
    for fee in c['commission_scenarios']:
        for slip in c['slippage_bps']:
            for year in c['years']:
                group = {r['arm']: r for r in rows if r['year'] == year and r['fee_scenario'] == fee and r['slippage_bps'] == slip}
                model, control = group['existing_momentum'], group['equal_vol_target']
                delta = {s: model['assets'][s]['net_pnl_after_exit_haircut_cny'] - control['assets'][s]['net_pnl_after_exit_haircut_cny'] for s in assets}
                paired.append({'year': year, 'fee_scenario': fee, 'slippage_bps': slip,
                               'net_advantage_by_asset_cny': delta, 'total_net_advantage_cny': sum(delta.values())})
    omission = []
    for fee in c['commission_scenarios']:
        for slip in c['slippage_bps']:
            selected = [r for r in paired if r['fee_scenario'] == fee and r['slippage_bps'] == slip]
            for excluded in c['years']:
                remainder = [r['total_net_advantage_cny'] for r in selected if r['year'] != excluded]
                omission.append({'fee_scenario': fee, 'slippage_bps': slip, 'excluded_year': excluded,
                                 'remaining_median_advantage_cny': statistics.median(remainder),
                                 'remaining_positive_years': sum(x > .01 for x in remainder)})
    result = {'experiment_id': 'CN-ATTRIBUTION-0001', 'verdict': 'RESEARCH', 'source_sha256': sha256(args.source.read_bytes()).hexdigest(),
        'implementation_sha256': {name: sha256(Path(name).read_bytes()).hexdigest() for name in ['scripts/attribute_cn_value.py', 'src/aoae/asset_attribution.py']},
        'reconciled_paths': len(rows), 'maximum_daily_reconciliation_error_cny': largest,
        'runs': rows, 'paired_asset_attribution': paired, 'leave_one_year_out_diagnostic': omission,
        'limits': ['Attribution only, no new signals or strategy trials.', 'Same reused years/cost/action/fill assumptions as source; not clean OOS.',
                   'Asset PnL is not causal timing alpha; no factor regression or neutrality asserted.',
                   'Removing a contribution arithmetically is NOT rerunning a portfolio without that asset.',
                   'Year omission is descriptive, not independent validation or a significance test.',
                   'Gross cashflow PnL uses actually cost-constrained holdings, not a rerun without fees.'],
        'capital_authorized': False, 'orders_authorized': False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'paths': len(rows), 'reconciliation_error': largest, 'base_paired': [r for r in paired if r['fee_scenario']=='screenshot_stress' and r['slippage_bps']==30]}, indent=2))


if __name__ == '__main__':
    main()
