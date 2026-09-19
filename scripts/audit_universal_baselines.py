"""Standard-library-only independent wealth/cost/decomposition audit."""
import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
import struct


def audit(record):
    paths = {p['sha256_float64_le']: p for p in record['paths']}
    config = record['config']
    largest_error = 0.
    for path in record['paths']:
        x = path['price_relatives']
        packed = b''.join(struct.pack('<d', v) for row in x for v in row)
        if sha256(packed).hexdigest() != path['sha256_float64_le']:
            raise ValueError('synthetic data digest mismatch')
        crp = sum(math.log(sum(row) / 2) for row in x)
        weighted = sum(sum(math.log(v) for v in row) / 2 for row in x)
        if abs(crp - weighted - path['decomposition_equal_daily']['exact_diversification_log_growth']) > 1e-9:
            raise ValueError('decomposition identity mismatch')
        # Independent finite-expert wealth average and sequential capital mixture.
        k = config['grid_points']
        expert = [1.] * k
        allocator = 1.
        for a, b in x:
            total = sum(expert)
            allocation_a = sum(value * (i / (k - 1)) for i, value in enumerate(expert)) / total
            allocator *= allocation_a * a + (1 - allocation_a) * b
            expert = [value * ((i / (k - 1)) * a + (1 - i / (k - 1)) * b) for i, value in enumerate(expert)]
        if abs(math.log(allocator) - math.log(sum(expert) / k)) > 1e-9:
            raise ValueError('independent universal identity mismatch')
    for run in record['runs']:
        x = paths[run['path_sha256']]['price_relatives']
        previous_wealth, old = 1., [0., 0., 1.]
        fees = turnover_sum = log_fee = 0.
        for row, after, target, saved_turn in zip(x, run['wealth_path'], run['executed_weights_including_cash'], run['turnover_path'], strict=True):
            growth = target[0] * row[0] + target[1] * row[1] + target[2]
            mu = after / previous_wealth / growth
            turnover = sum(abs(mu * target[i] - old[i]) for i in range(2))
            error = abs(1 - mu - turnover * run['cost_rate_per_traded_notional'])
            largest_error = max(largest_error, error, abs(turnover - saved_turn))
            cap = config['costs']['maximum_participation'] * config['costs']['volume_to_account_equity']
            if error > 1e-10 or abs(turnover - saved_turn) > 1e-10 or turnover > cap + 1e-10:
                raise ValueError('self-financing or participation mismatch')
            fees += previous_wealth * (1 - mu)
            turnover_sum += turnover
            log_fee -= math.log(mu)
            old = [target[0] * row[0] / growth, target[1] * row[1] / growth, target[2] / growth]
            previous_wealth = after
        nm = run['net_synthetic_proxy']
        if abs(fees - nm['transaction_cost_initial_wealth_units']) > 1e-9 or abs(turnover_sum - nm['turnover_sum_absolute_traded_fraction']) > 1e-9 or abs(log_fee - nm['log_fee_drag']) > 1e-9:
            raise ValueError('cost summary mismatch')
        if run['strategy'] == 'bcrp_ex_post' and run['information_class'] != 'EX_POST_OPTIMUM_NOT_TRADABLE':
            raise ValueError('oracle mislabeled tradable')
    return {'status': 'PASS', 'checked_costed_runs': len(record['runs']), 'maximum_accounting_error': largest_error,
            'scope': 'Independent arithmetic/finite-mixture identities, oracle labelling and synthetic participation only; not economic OOS validation.',
            'capital_authorized': False, 'orders_authorized': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--result', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    payload = args.result.read_bytes()
    record = json.loads(payload)
    root = Path(__file__).resolve().parents[1]
    for relative, expected in record['source_sha256'].items():
        if sha256((root / relative).read_bytes()).hexdigest() != expected:
            raise ValueError('implementation changed after result')
    result = audit(record)
    result['result_sha256'] = sha256(payload).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
