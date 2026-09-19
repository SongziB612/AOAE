"""Read-only verified journal-to-manual-ticket bridge; no capital promotion."""
import json
from pathlib import Path
import sqlite3
from contextlib import closing

from aoae.forward_journal import digest
from aoae.manual_ticket import prepare
from aoae.paired_forward import admit_signal, timestamp
from aoae.shadow_cycle import reduce_shadow


def read_shadow(path):
    path = Path(path).resolve(strict=True)
    # A read transaction presents one consistent snapshot even if the collector runs.
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        db.execute('BEGIN')
        rows = db.execute('SELECT * FROM events ORDER BY seq').fetchall()
    state, head, last, count = None, '0' * 64, None, 0
    reviews = []
    for seq, key, at, payload, previous, event_hash, state_hash in rows:
        event, when = json.loads(payload), timestamp(at)
        if seq != count + 1 or previous != head or (last and when < last):
            raise ValueError('journal sequence/time corrupt')
        if digest({'key': key, 'at': at, 'event': event, 'previous': previous}) != event_hash:
            raise ValueError('journal payload corrupt')
        state = reduce_shadow(state, event, at)
        if digest(state) != state_hash:
            raise ValueError('journal state mismatch')
        if event['kind'] == 'PRESAVE_SIGNAL':
            reviews.append(event['review'])
        head, last, count = event_hash, when, seq
    if state is None:
        raise ValueError('empty journal')
    return {'state': state, 'head': head, 'events': count, 'reviews': reviews}


def prepare_from_journal(root, audit, freeze, fee_record, snapshot, now):
    """Never use the paper ledger's capital/holdings as the human account balance."""
    state = audit['state']
    if state['freeze'] != freeze:
        raise ValueError('freeze differs from journal')
    request = {'signal': None, 'journal_head': audit['head'], 'journal_events': audit['events'],
               'classification': 'READ_ONLY_JOURNAL_BRIDGE_PAPER_ONLY'}
    signal = state['pending_signal']
    if signal is None:
        return prepare(request, now)
    if not snapshot:
        raise ValueError('fresh account and quote snapshot required; paper balances cannot substitute')
    raw = {k: v for k, v in signal.items() if k not in ('signal_id', 'captured_at_utc', 'capital_authorized')}
    captured = signal['captured_at_utc']
    if admit_signal(raw, freeze, captured)['signal_id'] != signal['signal_id']:
        raise ValueError('saved signal identity mismatch')
    review = next((r for r in audit['reviews'] if digest(r) == raw['review_evidence_sha256']), None)
    if not review:
        raise ValueError('missing signal review')
    for name, expected in review['source_sha256'].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise ValueError('missing or outside-workspace reviewed source')
        from hashlib import sha256
        if sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('reviewed source changed')
    if fee_record['confirmation_status'] != 'USER_CONFIRMED_EFFECTIVE_NOT_BROKER_API_VERIFIED':
        raise ValueError('fee confirmation missing')
    request.update(signal=raw, captured_at=captured, freeze=freeze,
                   arm='causal_total_return_momentum_overlay', account=snapshot['account'],
                   quotes=snapshot['quotes'], fees=fee_record['fees'], fee_record_sha256=digest(fee_record))
    return prepare(request, now)
