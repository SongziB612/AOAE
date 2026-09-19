"""Timestamp and hash current local raw-data evidence for the frozen candidate.

No retrospective signals, no fills, no orders, no claim of automatic trading.
Runs separately from frozen/legacy paper pipelines. Never rewrites their files.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

import pandas as pd
import numpy as np

from aoae.paired_forward import freshness, initial_accounts
from aoae.research_freeze import verify_freeze


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--data-dir', type=Path, required=True)
    p.add_argument('--expected-market-date', required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = args.output_dir.resolve()
    if not out.is_relative_to(root) or out == root:
        raise ValueError('output outside workspace')
    freeze_path = root / 'research/prospective/0003-raw-price-300k-paired-forward/freeze.json'
    freeze = json.loads(freeze_path.read_text(encoding='utf-8'))
    if verify_freeze(root, freeze)['status'] != 'INTACT':
        raise ValueError('freeze invalidated')
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    symbols = ('510300', '510500', '159915', '513500', '518880', '511010')
    if set(manifest['files']) != set(symbols):
        raise ValueError('incomplete universe')
    hashes = {}
    for symbol in symbols:
        path = args.data_dir / (symbol + '.csv')
        hashes[symbol] = sha256(path.read_bytes()).hexdigest()
        if hashes[symbol] != manifest['files'][symbol]['sha256']:
            raise ValueError('snapshot hash mismatch')
        frame = pd.read_csv(path)
        if frame.empty or frame.date.duplicated().any() or frame.date.tolist() != sorted(frame.date.tolist()):
            raise ValueError('invalid dates')
        if str(frame.date.iloc[-1]) != manifest['files'][symbol]['last_market_date']:
            raise ValueError('manifest date mismatch')
        if not np.isfinite(frame[['open', 'close']].to_numpy(dtype=float)).all() or (frame[['open', 'close']] <= 0).any().any():
            raise ValueError('invalid price')
    now = datetime.now(timezone.utc)
    status = freshness(manifest['files'], args.expected_market_date)
    record = {'experiment_id': 'PRO-0003-EVIDENCE-COLLECTOR-0001',
        'captured_at_utc': now.isoformat(), 'expected_market_date': args.expected_market_date,
        'actual_market_dates': sorted({r['last_market_date'] for r in manifest['files'].values()}),
        'freshness_status': status, 'freeze_sha256': sha256(freeze_path.read_bytes()).hexdigest(),
        'manifest_sha256': sha256(args.manifest.read_bytes()).hexdigest(), 'price_sha256': hashes,
        'signal_status': 'NOT_ADMITTED_CALENDAR_AND_CORPORATE_ACTION_REVIEW_REQUIRED',
        'observed_forward_signals': 0, 'observed_forward_fills': 0,
        'initial_cash_account_templates': initial_accounts(freeze),
        'templates_are_not_running_account_states': True,
        'source_sha256': {name: sha256((root / name).read_bytes()).hexdigest() for name in
            ['scripts/collect_paired_forward.py', 'src/aoae/paired_forward.py']},
        'capital_authorized': False, 'orders_authorized': False, 'broker_connection_authorized': False,
        'limits': ['Local acquisition timestamp is not vendor publication time.',
                   'Expected date is explicitly supplied, not an inferred exchange calendar.',
                   'No signal backfill or invented opening fills. No strategy scoring in this collector.',
                   'Collector does not yet certify raw adjustment/action changes or automatically advance ledgers.']}
    out.mkdir(parents=True, exist_ok=True)
    path = out / (now.strftime('%Y%m%dT%H%M%S%fZ') + '.json')
    with path.open('x', encoding='utf-8') as stream:
        json.dump(record, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'record': str(path), 'freshness': status, 'actual_market_dates': record['actual_market_dates'], 'signals': 0, 'fills': 0}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
