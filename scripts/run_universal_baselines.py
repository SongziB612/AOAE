"""Config-driven synthetic baseline suite; preserves every failure and oracle label."""
import argparse
from dataclasses import replace
from hashlib import sha256
from importlib.metadata import version
import json
from pathlib import Path

import numpy as np

from aoae.universal import SyntheticCosts, bcrp, run_portfolio, two_asset_grid, universal_weights
from aoae.universal_metrics import decomposition, metrics
from aoae.universal_synthetic import generate


def experiment(config):
    if any(config.get(k) is not False for k in ('capital_authorized', 'orders_authorized', 'broker_connection_authorized')):
        raise ValueError('research permissions must be false')
    if not config.get('development_only') or config['periods'] < 30:
        raise ValueError('this runner is only for synthetic development')
    costs = SyntheticCosts(**config['costs'])
    costs.validate()
    grid = two_asset_grid(config['grid_points'])
    equal = np.array([.5, .5])
    runs, paths, checks = [], [], []
    for world in config['worlds']:
        for seed in config['seeds']:
            x = generate(world, config['periods'], seed)
            digest = sha256(np.asarray(x, dtype='<f8').tobytes()).hexdigest()
            oracle = bcrp(x)
            up, mixture_log = universal_weights(x, grid)
            variants = {'fixed_asset0_buy_hold': (np.array([1., 0.]), None),
                        'equal_buy_hold': (equal, None), 'equal_daily': (equal, 1),
                        'equal_5session': (equal, 5), 'equal_21session': (equal, 21),
                        'bcrp_ex_post': (oracle['weights'], 1), 'universal_grid': (up, 1)}
            if set(config['variants']) != set(variants):
                raise ValueError('configured variant set differs from implemented baselines')
            gross = {name: run_portfolio(x, weights, frequency) for name, (weights, frequency) in variants.items()}
            grid_best = float(np.log(x @ grid.T).sum(axis=0).max())
            bh_identity = float(equal @ np.prod(x, axis=0))
            check = {'world': world, 'seed': seed,
                     'buy_hold_identity': bool(abs(gross['equal_buy_hold']['wealth'][-1] - bh_identity) < 1e-9 * max(1., bh_identity)),
                     'universal_mixture_identity': bool(abs(np.log(gross['universal_grid']['wealth'][-1]) - mixture_log) < 1e-9),
                     'finite_expert_log_regret_bound': bool(grid_best - mixture_log <= np.log(len(grid)) + 1e-9),
                     'bcrp_not_below_grid': bool(oracle['log_wealth'] + 1e-8 >= grid_best),
                     'bcrp_optimality_gap_bound': oracle['log_optimality_gap_bound']}
            if not all(check[k] for k in ['buy_hold_identity', 'universal_mixture_identity', 'finite_expert_log_regret_bound', 'bcrp_not_below_grid']):
                raise ValueError('mathematical identity audit failed')
            checks.append(check)
            decomp = decomposition(x, equal)
            paths.append({'world': world, 'seed': seed, 'sha256_float64_le': digest, 'price_relatives': x.tolist(), 'decomposition_equal_daily': decomp,
                          'bcrp_ex_post_weights': oracle['weights'].tolist(), 'grid_log_gap_to_continuous_bcrp': oracle['log_wealth'] - grid_best})
            for multiplier in config['cost_multipliers']:
                if not np.isfinite(multiplier) or multiplier < 1:
                    raise ValueError('cost multipliers must be finite and at least one')
                stressed = replace(costs, commission_bps=costs.commission_bps * multiplier,
                                   half_spread_bps=costs.half_spread_bps * multiplier,
                                   slippage_bps=costs.slippage_bps * multiplier,
                                   impact_bps_at_full_volume=costs.impact_bps_at_full_volume * multiplier)
                for name, (weights, frequency) in variants.items():
                    net = run_portfolio(x, weights, frequency, stressed)
                    gm, nm = metrics(gross[name], config['periods_per_year'], config['distress_threshold']), metrics(net, config['periods_per_year'], config['distress_threshold'])
                    runs.append({'world': world, 'seed': seed, 'path_sha256': digest, 'strategy': name,
                                 'cost_multiplier': multiplier, 'cost_rate_per_traded_notional': stressed.rate,
                                 'information_class': 'EX_POST_OPTIMUM_NOT_TRADABLE' if name == 'bcrp_ex_post' else 'ONLINE_SYNTHETIC_NOT_EMPIRICAL_OOS',
                                 'gross_mathematical_diagnostic': gm, 'net_synthetic_proxy': nm,
                                 'gross_minus_net_log_growth': gm['log_wealth_growth'] - nm['log_wealth_growth'],
                                 'wealth_path': net['wealth'].tolist(), 'turnover_path': net['turnover'].tolist(),
                                 'executed_weights_including_cash': net['executed_weights_including_cash'].tolist()})
    outcomes = []
    for world in config['worlds']:
        for multiplier in config['cost_multipliers']:
            subset = [r for r in runs if r['world'] == world and r['cost_multiplier'] == multiplier]
            by = {name: [r for r in subset if r['strategy'] == name] for name in config['variants']}
            outcomes.append({'world': world, 'cost_multiplier': multiplier,
                             'median_terminal_wealth': {name: float(np.median([r['net_synthetic_proxy']['terminal_wealth'] for r in group])) for name, group in by.items()},
                             'daily_rebalance_beats_equal_buy_hold_paths': sum(a['net_synthetic_proxy']['terminal_wealth'] > b['net_synthetic_proxy']['terminal_wealth'] for a, b in zip(by['equal_daily'], by['equal_buy_hold'])),
                             'raw_paths': len(config['seeds'])})
    counterexamples = [p['world'] for p in paths if p['decomposition_equal_daily']['exact_diversification_log_growth'] > 1e-8 and p['decomposition_equal_daily']['crp_log_growth'] < 0]
    return {'experiment_id': config['experiment_id'], 'verdict': 'RESEARCH', 'evidence': 'INSUFFICIENT EVIDENCE FOR REAL CAPITAL',
            'unconditional_positive_rebalancing_claim': 'REJECT' if counterexamples else 'RESEARCH',
            'counterexample_worlds': sorted(set(counterexamples)),
            'classic_kin_ark_iroquois_replication': 'NOT_REPLICATED_RELIABLE_ORIGINAL_DATA_NOT_ADMITTED',
            'raw_path_count': len(paths), 'unique_generated_paths': len({p['sha256_float64_le'] for p in paths}),
            'costed_variant_evaluations': len(runs), 'effective_independent_market_count': 0,
            'multiple_testing': 'All variants retained; development suite only, no p-values or selection claims; no final holdout used.',
            'paths': paths, 'runs': runs, 'identity_checks': checks, 'summary': outcomes,
            'limits': ['No real data, order-book or actual ETF capacity evidence.', 'Finite grid is not exact continuous universal integration.', 'BCRP is a gross ex-post optimum; costed BCRP is not net-optimal.', 'Universal expert scores ignore their own costs; account pays stated costs.', 'Fractional units and synthetic turnover caps are not broker fills.', 'Future ruin probability and real-market ESS remain unknown.', 'No regime, Kelly sizing, factor neutralization or ML claims.'],
            'capital_authorized': False, 'orders_authorized': False, 'broker_connection_authorized': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    config = json.loads(args.config.read_text(encoding='utf-8'))
    result = experiment(config)
    root = Path(__file__).resolve().parents[1]
    source_files = ['src/aoae/universal.py', 'src/aoae/universal_metrics.py', 'src/aoae/universal_synthetic.py', 'scripts/run_universal_baselines.py']
    result['config'] = config
    result['config_sha256'] = sha256(args.config.read_bytes()).hexdigest()
    result['source_sha256'] = {p: sha256((root / p).read_bytes()).hexdigest() for p in source_files}
    result['package_versions'] = {p: version(p) for p in ['numpy', 'scipy']}
    payload = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        stream.write(payload)
    print(json.dumps({k: result[k] for k in ['verdict', 'raw_path_count', 'unique_generated_paths', 'costed_variant_evaluations', 'unconditional_positive_rebalancing_claim', 'counterexample_worlds', 'summary']}, indent=2))


if __name__ == '__main__':
    main()
