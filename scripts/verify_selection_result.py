"""Independent scalar recomputation; deliberately does not import selection_audit."""
import argparse
from hashlib import sha256
from itertools import combinations
import json
from math import exp, sqrt
from pathlib import Path
from statistics import mean, stdev

from scipy.stats import norm, rankdata


def score(values):
    return mean(values) / stdev(values)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    report = json.loads(args.report.read_text(encoding='utf-8'))
    source = json.loads(args.source.read_text(encoding='utf-8'))
    for path, expected in report['source_sha256'].items():
        if sha256(Path(path).read_bytes()).hexdigest() != expected:
            raise ValueError('report input changed: ' + path)
    if str(args.source) not in report['source_sha256']:
        raise ValueError('source is not bound by report')
    config = source['config']
    checks = []
    for item in report['rows']:
        path = args.report.parent / item['matrix']
        if sha256(path.read_bytes()).hexdigest() != report['matrix_sha256'][item['matrix']]:
            raise ValueError('matrix hash mismatch')
        matrix = json.loads(path.read_text())
        selected = [r for r in source['runs'] if (r['year'], r['fee_scenario'], r['slippage_bps']) ==
                    (item['year'], item['fee'], item['slippage_bps'])]
        columns = []
        for arm in matrix['columns']:
            matches = [r for r in selected if r['arm'] == arm]
            if len(matches) != 1 or matches[0]['dates'] != matrix['dates']:
                raise ValueError('incomparable source run')
            run = matches[0]
            values = list(run['equity_cny'])
            values[-1] = config['initial_cny'] + run['net_pnl_after_exit_haircut_cny']
            previous, returns = config['initial_cny'], []
            for value in values:
                returns.append(value / previous - 1)
                previous = value
            columns.append(returns)
        error = max(abs(columns[j][i] - row[j]) for i, row in enumerate(matrix['net_returns'])
                    for j in range(len(columns)))
        n, blocks = len(columns[0]), item['pbo']['blocks']
        # Construct block membership without numpy.array_split or production helper.
        q, remainder = divmod(n, blocks)
        memberships = [b for b in range(blocks) for _ in range(q + int(b < remainder))]
        losses = []
        for chosen in combinations(range(blocks), blocks // 2):
            inside = [i for i, b in enumerate(memberships) if b in chosen]
            outside = [i for i, b in enumerate(memberships) if b not in chosen]
            train = [score([c[i] for i in inside]) for c in columns]
            test = [score([c[i] for i in outside]) for c in columns]
            winners = [j for j, s in enumerate(train) if s == max(train)]
            ranks = rankdata(test, method='average')
            losses.append(mean(1.0 if ranks[j] < (len(columns)+1)/2 else
                               0.5 if ranks[j] == (len(columns)+1)/2 else 0.0 for j in winners))
        pbo_error = abs(mean(losses) - item['pbo']['subset_pbo'])
        sr_all = [score(c) for c in columns]
        trial_variance = stdev(sr_all) ** 2
        r = columns[0]
        sr, center = score(r), mean(r)
        m2 = mean([(v-center)**2 for v in r])
        skew = mean([(v-center)**3 for v in r]) / m2**1.5
        kurt = mean([(v-center)**4 for v in r]) / m2**2
        errors = []
        for dsr in item['model_dsr']:
            trials = dsr['assumed_independent_trials']
            gamma = 0.5772156649015329
            benchmark = 0 if trials == 1 else sqrt(trial_variance) * (
                (1-gamma)*norm.ppf(1-1/trials) + gamma*norm.ppf(1-1/(trials*exp(1))))
            observed = norm.cdf((sr-benchmark)*sqrt(n-1) / sqrt(1-skew*sr+(kurt-1)*sr**2/4))
            errors.append(abs(float(observed) - dsr['dsr_iid_sensitivity']))
        checks.append({'matrix': item['matrix'], 'return_error': error, 'pbo_error': pbo_error,
                       'dsr_error': max(errors), 'partitions': len(losses)})
    passed = bool(checks) and all(max(c['return_error'], c['pbo_error'], c['dsr_error']) < 1e-10 for c in checks)
    output = {'status': 'PASS' if passed else 'FAIL', 'checks': checks,
              'input_sha256': {str(p): sha256(p.read_bytes()).hexdigest() for p in (args.report, args.source, Path(__file__))},
              'limits': 'Independent arithmetic implementation, same data and assumptions; not independent economic evidence, full-family validation or capital approval.',
              'capital_authorized': False}
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(output, stream, indent=2)
    print(json.dumps(output))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
