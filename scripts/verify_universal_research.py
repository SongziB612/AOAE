"""One command: tests, immutable reproductions, independent audits, data gate.

Exit 0 means engineering passed, NEVER profitability or live readiness.
Use --require-data-review to also fail if the metadata preflight is blocked.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

from aoae.universal_readiness import preflight


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--require-data-review', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = args.output_dir.resolve()
    if not out.is_relative_to(root) or out == root:
        raise ValueError('output must be a new child directory within repository')
    out.mkdir(parents=True, exist_ok=False)
    checks = []

    def run(name, command):
        print('running=' + name, flush=True)
        with (out / (name + '.log')).open('x', encoding='utf-8') as log:
            result = subprocess.run([sys.executable, *command], cwd=root,
                                    stdout=log, stderr=subprocess.STDOUT, timeout=600)
        checks.append({'name': name, 'passed': result.returncode == 0,
                       'returncode': result.returncode})
        if result.returncode:
            raise RuntimeError(name + ' failed; see retained log')

    failure = None
    readiness = None
    try:
        run('dependencies', ['-m', 'pip', 'check'])
        run('tests', ['-m', 'unittest', 'discover', '-s', 'tests', '-v'])
        for name, config, runner, expected in [
            ('baseline', 'universal_synthetic.json', 'run_universal_baselines.py',
             'up-0001-synthetic-rejection/result-v2.json'),
            ('net_expert', 'net_expert_challenge.json', 'run_net_expert_challenge.py',
             'up-0002-net-expert-scoring/result-v1.json')
        ]:
            result = out / (name + '.json')
            run(name, ['scripts/' + runner, '--config', 'configs/' + config,
                       '--output', str(result)])
            original = root / 'research/experiments' / expected
            equal = result.read_bytes() == original.read_bytes()
            checks.append({'name': name + '_byte_reproduction', 'passed': equal,
                           'sha256': sha256(result.read_bytes()).hexdigest()})
            if not equal:
                raise ValueError(name + ' reproduction mismatch')
            run(name + '_accounting', ['scripts/audit_universal_baselines.py',
                '--result', str(result), '--output', str(out / (name + '-audit.json'))])
        run('net_scoring', ['scripts/audit_net_expert_scores.py', '--result',
            str(out / 'net_expert.json'), '--output', str(out / 'net-scoring-audit.json')])
        protocol_path = root / 'configs/universal_real_protocol.json'
        readiness = preflight(root, json.loads(protocol_path.read_text(encoding='utf-8')))
    except Exception as exc:
        failure = type(exc).__name__ + ': ' + str(exc)
    artifact_hashes = {p.name: sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir()) if p.is_file()}
    summary = {
        'engineering_status': 'FAIL' if failure else 'PASS',
        'failure': failure, 'checks': checks, 'artifacts_sha256': artifact_hashes,
        'protocol_sha256': sha256((root / 'configs/universal_real_protocol.json').read_bytes()).hexdigest(),
        'verifier_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
        'preflight_source_sha256': sha256((root / 'src/aoae/universal_readiness.py').read_bytes()).hexdigest(),
        'real_data_preflight': readiness,
        'research_verdict': 'RESEARCH',
        'capital_readiness': 'NOT_READY', 'capital_authorized': False,
        'orders_authorized': False,
        'interpretation': 'Engineering closure only; no real-data profitability validated or new final holdout accessed.'
    }
    with (out / 'summary.json').open('x', encoding='utf-8') as stream:
        json.dump(summary, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if failure else (2 if args.require_data_review and readiness['status'] == 'BLOCKED' else 0)


if __name__ == '__main__':
    sys.exit(main())
