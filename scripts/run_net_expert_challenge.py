"""One-mechanism challenge; all worlds/costs retained, no parameter search."""
import argparse
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

import numpy as np

from aoae.net_expert_allocator import net_expert_weights
from aoae.universal import SyntheticCosts, run_portfolio, two_asset_grid, universal_weights
from aoae.universal_metrics import decomposition, metrics
from aoae.universal_synthetic import generate


def experiment(config, progress=None):
    if any(config.get(k) is not False for k in ('capital_authorized', 'orders_authorized', 'broker_connection_authorized')):
        raise ValueError('capital and execution forbidden')
    if config['periods'] < 30 or config['arms'] != ['equal_daily', 'gross_scored_up', 'net_scored_up']:
        raise ValueError('unsupported experiment contract')
    base = SyntheticCosts(**config['costs'])
    base.validate()
    grid = two_asset_grid(config['grid_points'])
    rows, paths = [], []
    for world in config['worlds']:
        for seed in config['seeds']:
            if world == 'trend_reversal':
                x = np.tile([1.008, .998], (config['periods'], 1))
                x[config['periods'] // 2:] = [.998, 1.008]
            else:
                x = generate(world, config['periods'], seed)
            digest = sha256(np.asarray(x, dtype='<f8').tobytes()).hexdigest()
            paths.append({'world': world, 'seed': seed, 'sha256_float64_le': digest,
                          'price_relatives': x.tolist(), 'decomposition_equal_daily': decomposition(x, np.array([.5, .5]))})
            gross_weights, _ = universal_weights(x, grid)
            for multiplier in config['cost_multipliers']:
                if not np.isfinite(multiplier) or multiplier < 1:
                    raise ValueError('invalid cost multiplier')
                costs = replace(base, commission_bps=base.commission_bps * multiplier,
                                half_spread_bps=base.half_spread_bps * multiplier,
                                slippage_bps=base.slippage_bps * multiplier,
                                impact_bps_at_full_volume=base.impact_bps_at_full_volume * multiplier)
                net_weights, _ = net_expert_weights(x, grid, costs)
                for name, weights in [('equal_daily', [.5, .5]), ('gross_scored_up', gross_weights), ('net_scored_up', net_weights)]:
                    net = run_portfolio(x, weights, 1, costs)
                    gross = run_portfolio(x, weights, 1, None)
                    rows.append({'world': world, 'seed': seed, 'path_sha256': digest,
                                 'strategy': name, 'cost_multiplier': multiplier,
                                 'cost_rate_per_traded_notional': costs.rate,
                                 'information_class': 'ONLINE_SYNTHETIC_NOT_EMPIRICAL_OOS',
                                 'net_synthetic_proxy': metrics(net, config['periods_per_year'], config['distress_threshold']),
                                 'gross_same_targets_mathematical_diagnostic': metrics(gross, config['periods_per_year'], config['distress_threshold']),
                                 'wealth_path': net['wealth'].tolist(),
                                 'turnover_path': net['turnover'].tolist(),
                                 'executed_weights_including_cash': net['executed_weights_including_cash'].tolist()})
        if progress:
            progress(world)
    summaries = []
    for world in config['worlds']:
        for cost in config['cost_multipliers']:
            group = [r for r in rows if r['world'] == world and r['cost_multiplier'] == cost]
            by = {arm: [r['net_synthetic_proxy'] for r in group if r['strategy'] == arm] for arm in config['arms']}
            new, old = by['net_scored_up'], by['gross_scored_up']
            summaries.append({'world': world, 'cost_multiplier': cost,
                              'median_terminal_wealth': {arm: float(np.median([m['terminal_wealth'] for m in by[arm]])) for arm in config['arms']},
                              'median_paired_net_minus_gross_log_growth': float(np.median([a['log_wealth_growth'] - b['log_wealth_growth'] for a, b in zip(new, old)])),
                              'median_paired_max_drawdown_change': float(np.median([a['max_drawdown'] - b['max_drawdown'] for a, b in zip(new, old)])),
                              'median_paired_ES_loss_change': float(np.median([a['expected_shortfall_loss_95'] - b['expected_shortfall_loss_95'] for a, b in zip(new, old)])),
                              'additional_distress_breaches': sum(a['observed_distress_breach'] and not b['observed_distress_breach'] for a, b in zip(new, old)),
                              'net_scored_beats_equal_paths': sum(a['log_wealth_growth'] > b['log_wealth_growth'] for a, b in zip(new, by['equal_daily']))})
    rule = config['development_rejection_rule']
    checks = {
        'all_groups_log_growth_noninferior': all(s['median_paired_net_minus_gross_log_growth'] >= rule['all_world_cost_groups_median_paired_log_improvement_at_least'] for s in summaries),
        'some_group_log_growth_improves': any(s['median_paired_net_minus_gross_log_growth'] > rule['at_least_one_group_median_paired_log_improvement_above'] for s in summaries),
        'all_groups_drawdown_noninferior': all(s['median_paired_max_drawdown_change'] >= rule['all_world_cost_groups_median_paired_max_drawdown_change_at_least'] for s in summaries),
        'no_additional_distress': all(s['additional_distress_breaches'] == 0 for s in summaries)}
    return {'experiment_id': config['experiment_id'], 'config': config,
            'candidate_upgrade_verdict': 'RESEARCH' if all(checks.values()) else 'REJECT',
            'verdict_scope': 'Promoting this exact net-score-only change under the locked development rule; not rejecting transaction cost modeling.',
            'real_capital_evidence': 'INSUFFICIENT EVIDENCE', 'checks': checks,
            'paths': paths, 'runs': rows, 'summary': summaries,
            'costed_variant_evaluations': len(rows),
            'unique_generated_paths': len({p['sha256_float64_le'] for p in paths}),
            'raw_paths': len(paths), 'independent_real_market_observations': 0,
            'cost_accounting': 'Virtual expert fees only affect scores. Actual allocator pays its own execution costs once; no summed expert fee debit.',
            'limits': ['Synthetic development only; seeds/variants are dependent and no significance is claimed.', 'Nominal CRP target mixture, not buy-and-hold shares of independently funded expert accounts.', 'No universal costless identity or asymptotic net growth guarantee is asserted.', 'Virtual experts each assume the same relative liquidity and fractional units; no real account capacity evidence.', 'No forgetting, cash expert, regime detector, Kelly sizing or hyperparameter tuning added.', 'Gross same-target diagnostic includes net-trained targets; it is not the old gross UP unless named gross_scored_up.'],
            'capital_authorized': False, 'orders_authorized': False, 'broker_connection_authorized': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    config = json.loads(args.config.read_text(encoding='utf-8'))
    result = experiment(config, lambda world: print('completed_world=' + world, flush=True))
    root = Path(__file__).resolve().parents[1]
    sources = ['src/aoae/net_expert_allocator.py', 'src/aoae/universal.py', 'src/aoae/universal_metrics.py', 'src/aoae/universal_synthetic.py', 'scripts/run_net_expert_challenge.py']
    result['source_sha256'] = {p: sha256((root / p).read_bytes()).hexdigest() for p in sources}
    result['config_sha256'] = sha256(args.config.read_bytes()).hexdigest()
    payload = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        stream.write(payload)
    print(json.dumps({k: result[k] for k in ['candidate_upgrade_verdict', 'checks', 'costed_variant_evaluations', 'unique_generated_paths', 'summary']}, indent=2))


if __name__ == '__main__':
    main()
