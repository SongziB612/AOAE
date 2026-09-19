"""One fixed state-conditioned challenger, paired costed synthetic comparisons."""
import argparse
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import numpy as np
from aoae.conditional_eg import conditional_weights, lagged_volatility_states
from aoae.exponentiated_portfolio import eg_weights
from aoae.universal import SyntheticCosts, run_portfolio
from aoae.universal_metrics import metrics
from aoae.universal_synthetic import generate


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    c = json.loads(args.config.read_text())
    base_path = Path(c['baseline_config'])
    b = json.loads(base_path.read_text())
    if c['capital_authorized'] is not False or not b['development_only']:
        raise ValueError('synthetic only')
    runs = []
    for world in b['worlds']:
        for seed in b['seeds']:
            x = generate(world, b['periods'], seed)
            states = lagged_volatility_states(x, c['state_window'], c['state_threshold'])
            variants = {'conditional_eg': (conditional_weights(x, states, c['learning_rate']), 1),
                        'plain_eg': (eg_weights(x, c['learning_rate']), 1),
                        'equal_daily': (np.array([.5,.5]), 1), 'equal_buy_hold': (np.array([.5,.5]), None)}
            for k in b['cost_multipliers']:
                costs = SyntheticCosts(**b['costs'])
                costs = replace(costs, commission_bps=costs.commission_bps*k, slippage_bps=costs.slippage_bps*k)
                for name, (w, frequency) in variants.items():
                    out = run_portfolio(x, w, frequency, costs)
                    runs.append({'world':world, 'seed':seed, 'cost_multiplier':k, 'strategy':name,
                                 'high_state_periods':int(states.sum()),
                                 'path_sha256':sha256(x.astype('<f8').tobytes()).hexdigest(),
                                 'metrics':metrics(out, b['periods_per_year'], b['distress_threshold'])})
    summary = []
    for world in b['worlds']:
        for k in b['cost_multipliers']:
            selected = [r for r in runs if r['world']==world and r['cost_multiplier']==k]
            differences = []
            for seed in b['seeds']:
                by = {r['strategy']:r['metrics']['log_wealth_growth'] for r in selected if r['seed']==seed}
                differences.append(by['conditional_eg']-by['plain_eg'])
            summary.append({'world':world, 'cost_multiplier':k, 'mean_paired_log_increment':float(np.mean(differences))})
    result = {'verdict':'RESEARCH' if all(s['mean_paired_log_increment']>0 for s in summary) else 'REJECT',
              'scope':'Reject or retain this fixed challenger screen, not all regime methods.',
              'config':c, 'baseline':b, 'runs':runs, 'summary':summary, 'capital_authorized':False,
              'independent_market_samples':0,
              'source_sha256':{str(p):sha256(p.read_bytes()).hexdigest() for p in
               [args.config, base_path, Path(__file__), Path('src/aoae/conditional_eg.py'),
                Path('src/aoae/exponentiated_portfolio.py'), Path('src/aoae/universal.py'),
                Path('src/aoae/universal_metrics.py'), Path('src/aoae/universal_synthetic.py')]}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as f:
        json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps({'verdict':result['verdict'],'runs':len(runs),'summary':summary}))


if __name__ == '__main__':
    main()
