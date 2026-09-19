"""Independent scalar two-asset virtual-expert scoring audit; no AOAE imports."""
import argparse
from hashlib import sha256
import itertools
import json
import math
from pathlib import Path


def independent_mu(old, target, rate):
    # Enumerate four buy/sell regions and solve their linear cost equation.
    # This intentionally does not reuse the production fixed-point method.
    for signs in itertools.product((-1., 1.), repeat=2):
        mu = (1 + rate * sum(signs[i] * old[i] for i in range(2))) / (1 + rate * sum(signs[i] * target[i] for i in range(2)))
        if 0 < mu <= 1 + 1e-12 and all(signs[i] * (mu * target[i] - old[i]) >= -1e-12 for i in range(2)):
            return mu
    raise ValueError('no valid self-financing region')


def audit(record):
    config = record['config']
    k = config['grid_points']
    grid = [(i / (k - 1), 1 - i / (k - 1)) for i in range(k)]
    paths = {p['sha256_float64_le']: p['price_relatives'] for p in record['paths']}
    cache = {}
    maximum = 0.
    audited = 0
    for run in record['runs']:
        if run['strategy'] != 'net_scored_up':
            continue
        key = run['path_sha256'], run['cost_rate_per_traded_notional']
        if key not in cache:
            expert_wealth = [1.] * k
            previous = [(0., 0.) for _ in range(k)]
            expected = []
            for row in paths[key[0]]:
                mass = sum(expert_wealth)
                expected.append([sum(expert_wealth[j] * grid[j][i] for j in range(k)) / mass for i in range(2)])
                for j, target in enumerate(grid):
                    mu = independent_mu(previous[j], target, key[1])
                    turnover = sum(abs(mu * target[i] - previous[j][i]) for i in range(2))
                    cap = config['costs']['maximum_participation'] * config['costs']['volume_to_account_equity']
                    if turnover > cap + 1e-10:
                        raise ValueError('independent score auditor requires nonbinding expert cap')
                    growth = sum(target[i] * row[i] for i in range(2))
                    expert_wealth[j] *= mu * growth
                    previous[j] = tuple(target[i] * row[i] / growth for i in range(2))
            cache[key] = expected
        for target, actual in zip(cache[key], run['executed_weights_including_cash'], strict=True):
            # In this suite allocator cap is nonbinding; otherwise do not certify.
            error = max(abs(target[0] - actual[0]), abs(target[1] - actual[1]), abs(actual[2]))
            if not math.isfinite(error) or error > 1e-9:
                raise ValueError('net-scored weight or nonbinding-cap assumption failed')
            maximum = max(maximum, error)
        audited += 1
    if not audited:
        raise ValueError('no net-scored runs')
    return {'status': 'PASS', 'net_scored_paths_audited': audited, 'unique_path_cost_pairs': len(cache),
            'maximum_weight_error': maximum,
            'scope': 'Independent scalar CRP cost-region solver and pre-return net-expert posterior; supports this nonbinding-cap two-asset suite only.',
            'capital_authorized': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--result', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    payload = args.result.read_bytes()
    result = audit(json.loads(payload))
    result['audited_result_sha256'] = sha256(payload).hexdigest()
    result['auditor_sha256'] = sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
