"""Transactional, replay-verified local shadow journal. Never sends orders."""
from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from aoae.paired_forward import initial_accounts, timestamp


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return sha256(canonical(value).encode()).hexdigest()


def reduce_event(state, event, recorded_at=None):
    """Only admitted cash-only checkpoints today; reject unsupported accounting."""
    state = deepcopy(state)
    if event['kind'] == 'INIT':
        if state is not None:
            raise ValueError('already initialized')
        return {'accounts': initial_accounts(event['freeze']),
                'freeze_sha256': event['freeze_sha256'], 'market_date': None,
                'checkpoints': 0, 'signals': 0, 'simulated_fills': 0,
                'capital_authorized': False, 'orders_authorized': False}
    if state is None:
        raise ValueError('journal not initialized')
    if event['kind'] != 'CASH_CHECKPOINT':
        raise ValueError('unsupported event; trading/action accounting not admitted')
    evidence = event['evidence']
    if evidence['freeze_sha256'] != state['freeze_sha256']:
        raise ValueError('freeze differs from account genesis')
    if evidence['freshness_status'] != 'CURRENT':
        raise ValueError('stale evidence')
    dates = evidence['actual_market_dates']
    if len(dates) != 1 or dates[0] != evidence['expected_market_date']:
        raise ValueError('market date mismatch')
    if state['market_date'] and dates[0] <= state['market_date']:
        raise ValueError('duplicate or backwards market day')
    if any(a['positions'] or a['simulated_fills'] for a in state['accounts'].values()):
        raise ValueError('cash checkpoint cannot value invested accounts')
    state['market_date'] = dates[0]
    state['price_sha256'] = evidence.get('price_sha256', {})
    state['checkpoints'] += 1
    state['status'] = 'CASH_ONLY_NO_ADMITTED_SIGNALS'
    # No return, interest, dividend, or forward trading-day claim is inferred.
    return state


class ForwardJournal:
    def __init__(self, path, reducer=reduce_event):
        self.path = Path(path)
        self.reducer = reducer
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY, event_key TEXT UNIQUE NOT NULL, recorded_at TEXT NOT NULL, payload TEXT NOT NULL, previous_hash TEXT NOT NULL, event_hash TEXT NOT NULL, state_hash TEXT NOT NULL)')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def _replay(self, db):
        state, head, last_time, count = None, '0' * 64, None, 0
        for seq, key, at, payload, previous, event_hash, state_hash in db.execute('SELECT * FROM events ORDER BY seq'):
            event = json.loads(payload)
            when = timestamp(at)
            if seq != count + 1 or previous != head or (last_time and when < last_time):
                raise ValueError('journal sequence/time/hash chain corrupt')
            if digest({'key': key, 'at': at, 'event': event, 'previous': previous}) != event_hash:
                raise ValueError('journal payload corrupt')
            state = self.reducer(state, event, at)
            if digest(state) != state_hash:
                raise ValueError('journal state mismatch')
            count, head, last_time = seq, event_hash, when
        return state, head, count

    def audit(self):
        with self.connect() as db:
            state, head, count = self._replay(db)
        return {'status': 'VERIFIED_LOCAL_REPLAY', 'events': count, 'head_sha256': head, 'state': state,
                'limit': 'Local hash chain is not external notarization and cannot detect whole-database rollback.'}

    def append(self, key, event):
        # Replay reads canonical JSON. Compute the original state from that same
        # representation: caller dict insertion order must not change economics.
        event = json.loads(canonical(event))
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            state, head, count = self._replay(db)
            existing = db.execute('SELECT payload FROM events WHERE event_key = ?', (key,)).fetchone()
            if existing:
                if existing[0] != canonical(event):
                    raise ValueError('event key reused with different content')
                return False
            at = datetime.now(timezone.utc).isoformat()
            updated = self.reducer(state, event, at)
            event_hash = digest({'key': key, 'at': at, 'event': event, 'previous': head})
            db.execute('INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?)',
                       (count + 1, key, at, canonical(event), head, event_hash, digest(updated)))
        return True
