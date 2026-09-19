"""Verify current real-data preparation without rerunning strategy searches."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = args.output_dir.resolve()
    data = args.data_dir.resolve()
    if out == root or not out.is_relative_to(root) or not data.is_relative_to(root / 'data'):
        raise ValueError('paths must remain in workspace')
    out.mkdir(parents=True, exist_ok=False)
    checks, failure = [], None
    commands = [
        ('tests', ['-m', 'unittest', 'discover', '-s', 'tests', '-v']),
        ('data_quality', ['scripts/audit_up_etf_capture.py', '--data-dir', str(data), '--output', str(out / 'data-quality.json')]),
        ('issuer_comparison', ['scripts/audit_spy_distributions.py', '--data-dir', str(data), '--output', str(out / 'issuer-comparison.json')]),
        ('execution', ['scripts/run_up_execution_checks.py', '--output', str(out / 'execution.json')]),
        ('execution_reproduction', ['scripts/run_up_execution_checks.py', '--output', str(out / 'execution-repeat.json')])
    ]
    try:
        for name, command in commands:
            print('running=' + name, flush=True)
            with (out / (name + '.log')).open('x', encoding='utf-8') as stream:
                completed = subprocess.run([sys.executable, *command], cwd=root, stdout=stream, stderr=subprocess.STDOUT, timeout=120)
            checks.append({'name': name, 'process_success': completed.returncode == 0})
            if completed.returncode:
                raise ValueError(name + ' failed; logs retained')
        if (out / 'execution.json').read_bytes() != (out / 'execution-repeat.json').read_bytes():
            raise ValueError('execution fixture reproduction mismatch')
    except Exception as exc:
        failure = type(exc).__name__ + ': ' + str(exc)
    result = {
        'engineering_status': 'FAIL' if failure else 'PASS', 'failure': failure, 'checks': checks,
        'economic_status': 'INSUFFICIENT_EVIDENCE', 'research_verdict': 'RESEARCH',
        'data_admitted': False, 'ready_for_capital': False,
        'all_controllable_preparation_complete': False,
        'remaining_internal_work': ['Resolve SPY issuer/vendor amount discrepancy and historical revision semantics',
                                    'Verify other ETF actions, raw-price semantics, calendar, vintages and data rights',
                                    'Integrate and test tax/FX/split handling as required by actual investor/market',
                                    'Freeze candidate, complete real historical/OOS matched-baseline and family-testing evaluation'],
        'remaining_external_dependencies': ['Verified broker/market access, fees, account currency and investor mandate',
                                            'Future forward-execution observations; historical replay cannot supply them'],
        'capital_authorized': False, 'orders_authorized': False,
        'artifacts_sha256': {p.name: sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir()) if p.is_file()},
        'source_sha256': {p: sha256((root / p).read_bytes()).hexdigest() for p in
            ['scripts/verify_up_preparation.py', 'scripts/capture_up_etf_research.py',
             'scripts/audit_up_etf_capture.py', 'scripts/audit_spy_distributions.py',
             'src/aoae/universal_temporal.py', 'src/aoae/universal_execution.py',
             'scripts/audit_universal_execution.py', 'scripts/run_up_execution_checks.py']},
        'interpretation': 'Command/audit success is not data admission. Issuer REVIEW_REQUIRED must remain unresolved until independently reconciled.'}
    with (out / 'summary.json').open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('artifacts_sha256', 'source_sha256')}, indent=2))
    return 1 if failure else 2


if __name__ == '__main__':
    sys.exit(main())
