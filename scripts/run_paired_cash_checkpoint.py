"""Persist current collector evidence in isolated, cash-only shadow accounts."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from aoae.forward_journal import ForwardJournal
from aoae.research_freeze import verify_freeze


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--record', type=Path, required=True)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--data-dir', type=Path, required=True)
    p.add_argument('--database', type=Path, required=True)
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    if not args.database.resolve().is_relative_to(root):
        raise ValueError('database outside workspace')
    freeze_path = root / 'research/prospective/0003-raw-price-300k-paired-forward/freeze.json'
    freeze_bytes = freeze_path.read_bytes()
    freeze = json.loads(freeze_bytes)
    if verify_freeze(root, freeze)['status'] != 'INTACT':
        raise ValueError('freeze changed')
    evidence = json.loads(args.record.read_text(encoding='utf-8'))
    if evidence['freeze_sha256'] != sha256(freeze_bytes).hexdigest():
        raise ValueError('wrong frozen candidate')
    if evidence['manifest_sha256'] != sha256(args.manifest.read_bytes()).hexdigest():
        raise ValueError('manifest changed')
    for symbol, expected in evidence['price_sha256'].items():
        if symbol not in ('510300', '510500', '159915', '513500', '518880', '511010'):
            raise ValueError('unknown symbol')
        if sha256((args.data_dir / f'{symbol}.csv').read_bytes()).hexdigest() != expected:
            raise ValueError('price evidence changed')
    if len(evidence['price_sha256']) != 6:
        raise ValueError('incomplete prices')
    if evidence['freshness_status'] != 'CURRENT':
        raise ValueError('stale evidence cannot advance journal')
    journal = ForwardJournal(args.database)
    journal.append('genesis', {'kind': 'INIT', 'freeze': freeze, 'freeze_sha256': evidence['freeze_sha256']})
    previous = journal.audit()['state']
    if previous['market_date'] == evidence['expected_market_date']:
        if previous['price_sha256'] != evidence['price_sha256']:
            raise ValueError('same-day provider revision requires explicit review')
        print(json.dumps({'status': 'SKIP_ALREADY_CHECKPOINTED', 'audit': journal.audit()}, indent=2))
        return
    event = {'kind': 'CASH_CHECKPOINT', 'evidence': evidence,
             'record_sha256': sha256(args.record.read_bytes()).hexdigest()}
    journal.append('market:' + evidence['expected_market_date'], event)
    print(json.dumps(journal.audit(), indent=2))


if __name__ == '__main__':
    main()
