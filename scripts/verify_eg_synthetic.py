"""Scalar EG and bisection cash ledger; no production allocator/ledger imports."""
import argparse
from hashlib import sha256
import json
from math import exp, log
from pathlib import Path
from statistics import stdev
from aoae.universal_synthetic import generate


def replay(rows, name, grid_size, rate, state_config=None):
    cash_weights = [0., 0., 1.]
    eg = [.5, .5]
    banks = [[.5, .5], [.5, .5]]
    past_market_logs = []
    experts = [1.] * grid_size
    wealth, fees, turnover = 1., 0., 0.
    for t, row in enumerate(rows):
        if name == 'conditional_eg':
            window = state_config['state_window']
            state = int(t >= window and stdev(past_market_logs[-window:]) >= state_config['state_threshold'])
            eg = banks[state].copy()
        if name.startswith('eg_') or name in ('plain_eg', 'conditional_eg'):
            target = eg + [0.]
        elif name == 'equal_buy_hold' and t > 0:
            target = cash_weights.copy()
        elif name == 'universal_grid':
            a = sum(v * (i/(grid_size-1)) for i, v in enumerate(experts)) / sum(experts)
            target = [a, 1-a, 0.]
        else:
            target = [.5, .5, 0.]
        lo, hi = 0., 1.
        for _ in range(70):
            mu = (lo+hi)/2
            cost = rate * sum(abs(mu*target[i]-cash_weights[i]) for i in range(2))
            if mu + cost > 1:
                hi = mu
            else:
                lo = mu
        mu = (lo+hi)/2
        traded = sum(abs(mu*target[i]-cash_weights[i]) for i in range(2))
        if traded > 1 + 1e-10:
            raise ValueError('audit supports current uncapped configuration only')
        growth = sum(target[i]*row[i] for i in range(2)) + target[2]
        fees += wealth * (1-mu)
        turnover += traded
        wealth *= mu*growth
        cash_weights = [target[i]*row[i]/growth for i in range(2)] + [target[2]/growth]
        if name.startswith('eg_') or name in ('plain_eg', 'conditional_eg'):
            eta = float(name[3:]) if name.startswith('eg_') else state_config['learning_rate']
            denominator = sum(eg[i]*row[i] for i in range(2))
            updated = [eg[i]*exp(eta*row[i]/denominator) for i in range(2)]
            eg = [v/sum(updated) for v in updated]
            if name == 'conditional_eg':
                banks[state] = eg.copy()
        past_market_logs.append(sum(log(v) for v in row)/len(row))
        if name == 'universal_grid':
            experts = [v*((i/(grid_size-1))*row[0]+(1-i/(grid_size-1))*row[1]) for i,v in enumerate(experts)]
    return wealth, fees, turnover


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--result', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    raw = args.result.read_bytes()
    r = json.loads(raw)
    for path, digest in r['source_sha256'].items():
        if sha256(Path(path).read_bytes()).hexdigest() != digest:
            raise ValueError('changed input: '+path)
    c = r.get('baseline_config', r.get('baseline'))
    if c['costs']['volume_to_account_equity'] * c['costs']['maximum_participation'] != 1:
        raise ValueError('unsupported capacity configuration')
    errors = []
    for run in r['runs']:
        x = generate(run['world'], c['periods'], run['seed'])
        if sha256(x.astype('<f8').tobytes()).hexdigest() != run['path_sha256']:
            raise ValueError('generated path mismatch')
        k, cost = run['cost_multiplier'], c['costs']
        rate = (k*(cost['commission_bps']+cost['slippage_bps'])+cost['half_spread_bps']+
                cost['impact_bps_at_full_volume']*cost['maximum_participation'])/10000
        wealth, fees, turnover = replay(x.tolist(), run['strategy'], c['grid_points'], rate, r['config'])
        m = run['metrics']
        errors.append(max(abs(wealth-m['terminal_wealth']), abs(fees-m['transaction_cost_initial_wealth_units']),
                          abs(turnover-m['turnover_sum_absolute_traded_fraction'])))
    out = {'status': 'PASS' if errors and max(errors)<1e-8 else 'FAIL', 'runs': len(errors),
           'maximum_absolute_error': max(errors), 'result_sha256': sha256(raw).hexdigest(),
           'auditor_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
           'scope': 'Independent EG/mixture target update and scalar costed terminal wealth/fees/turnover; same synthetic paths; other metrics not independently certified.',
           'capital_authorized': False}
    with args.output.open('x', encoding='utf-8') as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out))
    return 0 if out['status']=='PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
