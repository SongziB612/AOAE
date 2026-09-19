"""Risk of actual aggregated sleeve NAVs; correlation is not independent ESS."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import numpy as np


def describe(nav, initial):
    values = np.asarray(nav, dtype=float)
    if not len(values) or not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError('positive finite NAV required')
    changes = values / np.r_[initial, values[:-1]] - 1
    drawdowns = values / np.maximum.accumulate(np.r_[initial, values])[1:] - 1
    return {'net_pnl_cny': float(values[-1]-initial), 'maximum_drawdown': float(drawdowns.min()),
            'worst_day_return': float(changes.min()),
            'observed_tail_mean_loss_95': float(-np.sort(changes)[:max(1,int(np.ceil(len(changes)*.05)))].mean()),
            'log_wealth_growth': float(np.log(values[-1]/initial)),
            'risk_of_ruin_probability': None}, changes


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--small',type=Path,required=True)
    p.add_argument('--large',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    small,large=[json.loads(p.read_text()) for p in (args.small,args.large)]
    for r in (small,large):
        for path,digest in r['input_sha256'].items():
            if sha256(Path(path).read_bytes()).hexdigest()!=digest:
                raise ValueError('source changed: '+path)
    c=small['config']; arms=c['arms']; total=c['initial_cny']*len(arms)
    if total != large['config']['initial_cny']:
        raise ValueError('different total capital')
    results=[]
    for year in c['years']:
        for fee in c['commission_scenarios']:
            for slip in c['slippage_bps']:
                select=lambda data: [r for r in data['runs'] if (r['year'],r['fee_scenario'],r['slippage_bps'])==(year,fee,slip)]
                group=select(small); controls={r['arm']:r for r in select(large)}
                if len(group)!=len(arms) or {r['arm'] for r in group}!=set(arms):
                    raise ValueError('missing or duplicate sleeve')
                navs=[]; returns=[]
                for r in group:
                    if r['dates']!=group[0]['dates']:
                        raise ValueError('date mismatch')
                    nav=list(r['equity_cny']); nav[-1]=c['initial_cny']+r['net_pnl_after_exit_haircut_cny']
                    _,ret=describe(nav,c['initial_cny']); navs.append(nav); returns.append(ret)
                aggregate,_=describe(np.sum(navs,axis=0),total)
                correlation=np.corrcoef(returns)
                if not np.isfinite(correlation).all():
                    raise ValueError('degenerate correlation')
                eig=np.linalg.eigvalsh(correlation)
                comparisons={}
                for arm in ('existing_momentum','equal_monthly','equal_buy_hold','equal_vol_target'):
                    r=controls[arm]
                    if r['dates']!=group[0]['dates']:
                        raise ValueError('control calendar mismatch')
                    nav=list(r['equity_cny']); nav[-1]=total+r['net_pnl_after_exit_haircut_cny']
                    comparisons[arm]=describe(nav,total)[0]
                results.append({'year':year,'fee_scenario':fee,'slippage_bps':slip,'aggregate':aggregate,
                                'sleeve_order':[r['arm'] for r in group], 'correlation':correlation.tolist(),
                                'correlation_participation_ratio':float(eig.sum()**2/(eig@eig)),
                                'mean_pairwise_correlation':float(correlation[np.triu_indices(len(arms),1)].mean()),
                                'controls':comparisons})
    report={'status':'DESCRIPTIVE_REUSED_HISTORY','rows':results,'capital_authorized':False,
            'limits':['Terminal NAV includes estimated exit haircut; not observed exit.',
                      'Eigenvalue participation ratio measures descriptive correlation dimension, not effective sample size or number of independent strategies.',
                      'No risk-of-ruin forecast or factor-neutral alpha claim.'],
            'input_sha256':{str(p):sha256(p.read_bytes()).hexdigest() for p in (args.small,args.large,Path(__file__))}}
    with args.output.open('x',encoding='utf-8') as f:
        json.dump(report,f,indent=2,allow_nan=False)
    print(json.dumps([{'year':r['year'],'slip':r['slippage_bps'],'drawdown':r['aggregate']['maximum_drawdown'],
                       'equal_drawdown':r['controls']['equal_monthly']['maximum_drawdown'],
                       'mean_correlation':r['mean_pairwise_correlation'],'risk_dimension':r['correlation_participation_ratio']} for r in results]))


if __name__=='__main__':
    main()
