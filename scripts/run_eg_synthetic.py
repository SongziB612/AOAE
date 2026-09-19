"""Apply the missing EG baseline to existing falsification worlds, no live data."""
import argparse
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import numpy as np
from aoae.exponentiated_portfolio import eg_weights
from aoae.universal import SyntheticCosts, run_portfolio, universal_weights, two_asset_grid
from aoae.universal_metrics import metrics
from aoae.universal_synthetic import generate


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    config = json.loads(args.config.read_text())
    baseline = Path(config['baseline_config'])
    c = json.loads(baseline.read_text())
    if config['capital_authorized'] is not False or not c['development_only']:
        raise ValueError('synthetic research only')
    runs = []
    for world in c['worlds']:
        for seed in c['seeds']:
            x = generate(world, c['periods'], seed)
            variants = {'equal_daily': (np.array([.5, .5]), 1), 'equal_buy_hold': (np.array([.5, .5]), None),
                        'universal_grid': (universal_weights(x, two_asset_grid(c['grid_points']))[0], 1)}
            variants.update({f'eg_{eta}': (eg_weights(x, eta), 1) for eta in config['learning_rates']})
            for multiplier in c['cost_multipliers']:
                costs = SyntheticCosts(**c['costs'])
                costs = replace(costs, commission_bps=costs.commission_bps*multiplier,
                                slippage_bps=costs.slippage_bps*multiplier)
                for name, (weights, frequency) in variants.items():
                    net = run_portfolio(x, weights, frequency, costs)
                    runs.append({'world': world, 'seed': seed, 'cost_multiplier': multiplier, 'strategy': name,
                                 'path_sha256': sha256(x.astype('<f8').tobytes()).hexdigest(),
                                 'metrics': metrics(net, c['periods_per_year'], c['distress_threshold'])})
    report = {'verdict': 'RESEARCH', 'config': config, 'baseline_config': c, 'runs': runs,
              'capital_authorized': False, 'independent_market_samples': 0,
              'limits': ['Gross-gradient learner pays synthetic account costs but does not optimize them.',
                         'Not a real-data replication, Kelly policy, regime model or investable strategy.',
                         'Shared paths and deterministic repeated worlds are not independent evidence.'],
              'source_sha256': {str(p): sha256(p.read_bytes()).hexdigest() for p in
                               [args.config, baseline, Path(__file__), Path('src/aoae/exponentiated_portfolio.py'),
                                Path('src/aoae/universal.py'), Path('src/aoae/universal_synthetic.py'), Path('src/aoae/universal_metrics.py')]}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as f:
        json.dump(report, f, indent=2, allow_nan=False)
    print(json.dumps({'runs': len(runs), 'verdict': report['verdict']}))


if __name__ == '__main__':
    main()
