"""Bounded descriptive audit of existing paths. No tuning or holdout access."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import numpy as np
from aoae.selection_audit import comparable_matrix, cscv_pbo, deflated_sharpe


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--source', type=Path, default=Path('research/experiments/cn-value-0001/result-v1.json'),
                   help='Existing immutable comparable replay result; no new parameter search.')
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    if not output.is_relative_to(root) or output.exists():
        raise ValueError('new workspace directory required')
    source = args.source.resolve()
    if not source.is_relative_to(root):
        raise ValueError('source outside workspace')
    ledger_path = root / 'research/strategy-family-ledger.json'
    raw = json.loads(source.read_text(encoding='utf-8'))
    ledger = json.loads(ledger_path.read_text(encoding='utf-8'))
    for name, expected in raw['input_sha256'].items():
        if sha256((root / name).read_bytes()).hexdigest() != expected:
            raise ValueError('historical input changed: ' + name)
    c = raw['config']
    for symbol, expected in raw['price_sha256'].items():
        if sha256((root / c['data_dir'] / (symbol + '.csv')).read_bytes()).hexdigest() != expected:
            raise ValueError('historical prices changed')
    output.mkdir(parents=True)
    rows, artifacts = [], {}
    for year in c['years']:
        for fee in c['commission_scenarios']:
            for slip in c['slippage_bps']:
                selected = [r for r in raw['runs'] if (r['year'], r['fee_scenario'], r['slippage_bps']) == (year, fee, slip)]
                dates, matrix = comparable_matrix(selected, c['arms'], c['initial_cny'])
                name = f'{year}-{fee}-{slip}.json'
                payload = {'dates': dates, 'columns': c['arms'], 'net_returns': matrix.tolist(),
                           'scope': 'One independently reset year, four comparison arms, one cost scenario; not full search family.'}
                path = output / name
                path.write_text(json.dumps(payload, allow_nan=False), encoding='utf-8')
                artifacts[name] = sha256(path.read_bytes()).hexdigest()
                sr = matrix.mean(axis=0) / matrix.std(axis=0, ddof=1)
                item = {'year': year, 'fee': fee, 'slippage_bps': slip, 'matrix': name,
                        'dsr_scope': 'Sensitivity only: variance from four comparison arms, not full research population.',
                        'model_dsr': [deflated_sharpe(matrix[:, 0], n, float(sr.var(ddof=1))) for n in (6, 20, 100, 1000)]}
                # Boundary handling is explicit and cannot discard observations.
                # Fixed eight contiguous blocks, differing by at most one day.
                # Label this extension explicitly; no dates dropped or duplicated.
                item['pbo'] = cscv_pbo(matrix, 8, balanced=True)
                rows.append(item)
    inventory = []
    for spec in sorted((root / 'research/hypotheses').glob('*/spec.json')):
        result = spec.with_name('result.json')
        inventory.append({'id': spec.parent.name, 'spec_sha256': sha256(spec.read_bytes()).hexdigest(),
                          'result_present': result.exists(),
                          'result_sha256': sha256(result.read_bytes()).hexdigest() if result.exists() else None,
                          'comparable_to_current_matrix': 'NOT_ESTABLISHED'})
    report = {'status': 'DESCRIPTIVE_SUBSET_ONLY_FULL_FAMILY_BLOCKED', 'capital_authorized': False,
              'orders_authorized': False, 'clean_oos_observations': 0,
              'full_family_dsr': None, 'full_family_pbo': None, 'rows': rows,
              'trial_inventory': inventory, 'prior_family_ledger': ledger,
              'blockers': ['All historical parameter/search choices are not reconstructed.',
                           'Four comparison arms are not the six-plus historical economic candidates.',
                           'IID DSR does not correct serial dependence; CSCV is not a new chronological holdout.',
                           'Reused history and modeled fills cannot establish executable alpha.'],
              'matrix_sha256': artifacts,
              'source_sha256': {str(f.relative_to(root)): sha256(f.read_bytes()).hexdigest() for f in
                               (source, ledger_path, Path(__file__).resolve(), root / 'src/aoae/selection_audit.py')},
              'first_principles': {'payer': 'ETF exposure; incremental timing edge unproven',
                                   'risk_of_ruin': None, 'net_executable_alpha': None,
                                   'decision': 'Do not change frozen candidate or allocate capital from subset diagnostics.'}}
    (output / 'result.json').write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    print(json.dumps({'status': report['status'], 'matrices': len(rows), 'report': str(output / 'result.json')}))


if __name__ == '__main__':
    main()
