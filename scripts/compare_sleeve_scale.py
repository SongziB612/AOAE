"""No transfers/netting: aggregate independently executed smaller strategy books."""
import argparse
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--large', type=Path, required=True)
    p.add_argument('--small', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    large, small = [json.loads(p.read_text()) for p in (args.large, args.small)]
    for result in (large, small):
        for path, expected in result['input_sha256'].items():
            if sha256(Path(path).read_bytes()).hexdigest() != expected:
                raise ValueError('changed input: ' + path)
    a, b = large['config'], small['config']
    keys = ('years','arms','commission_scenarios','slippage_bps','lookback','target_volatility','reference','strategy_spec','data_dir')
    if any(a[k] != b[k] for k in keys) or large['price_sha256'] != small['price_sha256']:
        raise ValueError('incomparable experiments')
    factor = Decimal(str(b['initial_cny']))/Decimal(str(a['initial_cny']))
    if factor*len(a['arms']) != 1 or Decimal(str(b['pause_loss_cny']))/Decimal(str(a['pause_loss_cny'])) != factor:
        raise ValueError('capital or pause fraction differs')
    rows = []
    for year in a['years']:
        for fee in a['commission_scenarios']:
            for slip in a['slippage_bps']:
                group = []
                for result in (large,small):
                    chosen = [r for r in result['runs'] if (r['year'],r['fee_scenario'],r['slippage_bps'])==(year,fee,slip)]
                    if len(chosen)!=len(a['arms']) or {r['arm'] for r in chosen}!=set(a['arms']):
                        raise ValueError('missing/duplicate sleeve')
                    group.append({r['arm']:r for r in chosen})
                big, little = group
                all_runs = list(big.values()) + list(little.values())
                if any(r['dates']!=all_runs[0]['dates'] for r in all_runs):
                    raise ValueError('calendar mismatch')
                pnl = lambda r: Decimal(str(r['net_pnl_after_exit_haircut_cny']))
                actual = sum(pnl(r) for r in little.values())
                scaled = sum(pnl(r)*factor for r in big.values())
                rows.append({'year':year,'slippage_bps':slip,'fee_scenario':fee,
                             'segregated_sleeve_pnl_cny':str(actual),
                             'naively_scaled_large_accounts_pnl_cny':str(scaled),
                             'nonlinear_scale_difference_cny':str(actual-scaled),
                             'difference_vs_large_equal_monthly_cny':str(actual-pnl(big['equal_monthly'])),
                             'difference_vs_large_momentum_cny':str(actual-pnl(big['existing_momentum'])),
                             'sleeve_initial_total_cny': b['initial_cny']*len(b['arms']),
                             'maximum_independent_ledger_error':max(r['independent_ledger_max_error'] for r in little.values())})
    output={'status':'RESEARCH_ONLY_NO_TRANSFERS_OR_NETTING','rows':rows,
            'inputs':{str(p):sha256(p.read_bytes()).hexdigest() for p in (args.large,args.small,Path(__file__))},
            'limits':'Scale difference mixes discrete lots, minimum fees, idle cash and path-dependent decisions; not pure commission drag. Separate annual resets, no clean OOS.',
            'capital_authorized':False}
    with args.output.open('x',encoding='utf-8') as f:
        json.dump(output,f,indent=2)
    print(json.dumps(rows))


if __name__=='__main__':
    main()
