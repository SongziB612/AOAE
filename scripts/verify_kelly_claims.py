"""Independent Decimal wealth recursion and binomial verification."""
import hashlib
import json
import math
from decimal import Decimal, localcontext
from pathlib import Path


def main():
    source = Path('research/experiments/kelly-claims-0001/result-v1.json')
    result = json.loads(source.read_text(encoding='utf-8'))
    for filename, expected in result['source_hashes'].items():
        assert hashlib.sha256(Path(filename).read_bytes()).hexdigest() == expected
    errors = []
    with localcontext() as context:
        context.prec = 70
        for row in result['rows'] + [result['wrong_edge_half_kelly_example']]:
            p, b, f, barrier = (Decimal(str(row[k])) for k in ('p', 'b', 'fraction', 'barrier'))
            n = row['bets']
            up, down, q = 1 + f * b, 1 - f, 1 - p
            terminal_loss = terminal_barrier = Decimal(0)
            for w in range(n + 1):
                wealth = up ** w * down ** (n - w)
                prob = Decimal(math.comb(n, w)) * p ** w * q ** (n - w)
                terminal_loss += prob * (wealth < 1)
                terminal_barrier += prob * (wealth <= barrier)
            # Backwards conditional probability of a future breach, using wealth
            # multiplication, not the production forward log-space absorption.
            future = {w: Decimal(up ** w * down ** (n - w) <= barrier) for w in range(n + 1)}
            for t in range(n - 1, -1, -1):
                future = {w: (Decimal(1) if up ** w * down ** (t - w) <= barrier
                              else q * future[w] + p * future[w + 1]) for w in range(t + 1)}
            expected = {'terminal_loss_probability': terminal_loss,
                        'terminal_barrier_probability': terminal_barrier,
                        'ever_barrier_probability': future[0],
                        'expected_log_growth_per_bet': p * up.ln() + q * down.ln()}
            errors.extend(abs(float(value) - row[key]) for key, value in expected.items())
    assert max(errors) < 1e-12, max(errors)
    audit = {'status': 'PASS', 'rows': 6, 'maximum_absolute_error': max(errors),
             'method': '70-digit Decimal backwards barrier recursion and terminal binomial sum',
             'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
             'verifier_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             'limitation': 'Checks hypothetical binary math only, not real strategy edge or execution'}
    target = source.with_name('independent-audit-v1.json')
    with target.open('x', encoding='utf-8') as stream:
        json.dump(audit, stream, indent=2)
    print(json.dumps(audit, indent=2))


if __name__ == '__main__':
    main()
