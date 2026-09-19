"""Deterministic falsification of supplied article; no strategy tuning."""
import argparse
import hashlib
import json
from pathlib import Path

from aoae.kelly_diagnostics import binary_diagnostic


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    rows = [binary_diagnostic(.55, 2, f) for f in (0, .02, .25, .325, .1625)]
    result = {
        'scope': 'IID binary hypothetical bets, known probabilities, not ETF performance',
        'assumptions': '100 bets; fixed net win +2 / loss -1 per unit staked; no fees, gaps, minimum orders; barrier 20% of initial capital',
        'source': 'https://www.theparticle.com/cs/bc/dsci/kelly_56.pdf',
        'rows': rows,
        'wrong_edge_half_kelly_example': binary_diagnostic(.2, 2, .1625),
        'half_to_full_log_growth_ratio': rows[4]['expected_log_growth_per_bet'] / rows[3]['expected_log_growth_per_bet'],
        'half_to_full_simple_variance_ratio': rows[4]['simple_return_variance'] / rows[3]['simple_return_variance'],
        'live_sizing_authorized': False,
        'source_hashes': {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in (
            'src/aoae/kelly_diagnostics.py', 'scripts/audit_kelly_claims.py', 'tests/test_kelly_diagnostics.py')},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
