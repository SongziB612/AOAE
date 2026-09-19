"""Record a deterministic corporate-action/settlement stress fixture, not PnL evidence."""
import argparse
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path

import pandas as pd

from aoae.universal_execution import CashAction, replay_next_open
if __package__:
    from scripts.audit_universal_execution import audit
else:
    from audit_universal_execution import audit


def experiment():
    days = pd.bdate_range('2024-01-02', periods=8)
    prices = pd.DataFrame({'A': [10., 10., 9., 9., 8., 5., 5., 5.],
                           'B': [20.] * 8}, index=days)
    caps = prices * 100
    targets = {str(days[1].date()): {'A': 1., 'B': 0.},
               str(days[3].date()): {'A': 0., 'B': 1.},
               str(days[4].date()): {'A': 1., 'B': 0.}}
    action = CashAction('A', str(days[2].date()), str(days[0].date()), str(days[5].date()), 1.)
    settings = {'initial': 10000., 'commission_bps': 5., 'minimum_fee': 1.,
                'adverse_bps': 10., 'settlement_sessions': 1, 'pause_loss': 1000.}
    result = replay_next_open(prices, prices, caps, targets, [action], **settings)
    record = {'dates': [str(d.date()) for d in days], 'symbols': list(prices.columns),
              'opens': prices.to_dict('records'), 'closes': prices.to_dict('records'),
              'opening_capacity': caps.to_dict('records'), 'targets': targets,
              'actions': [asdict(action)], 'settings': settings, 'result': result}
    return {'fixture': record, 'independent_audit': audit(record), 'verdict': 'RESEARCH',
            'interpretation': 'Deterministic engineering fixture; no real historical backtest, no independent market sample.',
            'capital_authorized': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    result = experiment()
    root = Path(__file__).resolve().parents[1]
    result['source_sha256'] = {p: sha256((root / p).read_bytes()).hexdigest() for p in
        ['src/aoae/universal_execution.py', 'scripts/audit_universal_execution.py',
         'scripts/run_up_execution_checks.py']}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(result['independent_audit'], indent=2))


if __name__ == '__main__':
    main()
