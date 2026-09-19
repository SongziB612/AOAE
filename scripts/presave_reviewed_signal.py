"""Generate and journal frozen weights from an explicitly reviewed bundle.

No --as-of clock override, no arbitrary submitted weights, no live orders.
This does not perform the independent source-content review itself.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from aoae.forward_journal import ForwardJournal
from aoae.research_freeze import verify_freeze
from aoae.reviewed_signal import build_event
from aoae.shadow_cycle import reduce_shadow


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--bundle', type=Path, required=True)
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    freeze = json.loads((root / 'research/prospective/0003-raw-price-300k-paired-forward/freeze.json').read_text(encoding='utf-8'))
    if verify_freeze(root, freeze)['status'] != 'INTACT':
        raise ValueError('freeze changed')
    bundle = json.loads(args.bundle.read_text(encoding='utf-8'))
    event = build_event(root, bundle, freeze, datetime.now(timezone.utc).isoformat())
    journal = ForwardJournal(root / 'data/runtime/paired_forward/engineering-shadow-v1.sqlite3', reducer=reduce_shadow)
    journal.append('PRESAVE_SIGNAL:' + event['review']['signal_day'], event)
    print(json.dumps({'status': 'PRESAVED_ENGINEERING_SIGNAL_NOT_CAPITAL_APPROVAL',
                      'signal_day': event['review']['signal_day'], 'capital_authorized': False}))


if __name__ == '__main__':
    main()
