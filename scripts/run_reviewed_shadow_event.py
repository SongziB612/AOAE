"""Append a source-hash-bound engineering event. Not a brokerage interface.

Review assertions still require a qualified independent content review; hashes
only detect changed files. Scheduled work uses run_paired_strategy_cycle.py.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

from aoae.forward_journal import ForwardJournal
from aoae.research_freeze import verify_freeze
from aoae.shadow_cycle import reduce_shadow
from aoae.source_timing import validate_source_timing


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--event', type=Path)
    p.add_argument('--init', action='store_true')
    p.add_argument('--audit', action='store_true')
    args = p.parse_args()
    if sum((args.event is not None, args.init, args.audit)) != 1:
        p.error('choose exactly one of --init, --event or --audit')
    root = Path(__file__).resolve().parents[1]
    freeze = json.loads((root / 'research/prospective/0003-raw-price-300k-paired-forward/freeze.json').read_text(encoding='utf-8'))
    if verify_freeze(root, freeze)['status'] != 'INTACT':
        raise ValueError('frozen strategy changed')
    journal = ForwardJournal(root / 'data/runtime/paired_forward/engineering-shadow-v1.sqlite3', reducer=reduce_shadow)
    if args.init:
        journal.append('genesis', {'kind': 'SHADOW_INIT', 'freeze': freeze})
    elif args.event:
        event = json.loads(args.event.read_text(encoding='utf-8'))
        if event['kind'] != 'MODELED_DAY':
            raise ValueError('use presave_reviewed_signal.py for computed signal weights')
        # Admission-only: historical journal replay remains unchanged. Hashes
        # alone do not establish that a source existed before the decision.
        validate_source_timing(event['review'], datetime.now(timezone.utc).isoformat())
        sources = event['review']['source_sha256']
        if not sources:
            raise ValueError('no source evidence')
        for name, expected in sources.items():
            path = (root / name).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                raise ValueError('missing/outside-workspace evidence')
            if sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError('source evidence changed')
        # Stable day-based key rejects conflicting rewrites. Clock is internal.
        key = event['kind'] + ':' + (event.get('day') or event['review']['signal_day'])
        journal.append(key, event)
    print(json.dumps(journal.audit(), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
