"""Build frozen weights from reviewed files rather than accepting typed weights."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json

import pandas as pd

from aoae.corporate_action_replay import Action
from aoae.etf_momentum import load_spec
from aoae.forward_journal import digest
from aoae.forward_signal import frozen_weights
from aoae.paired_forward import admit_signal
from aoae.source_timing import validate_source_timing


def month_end_pair(sessions, signal_day):
    dates = [datetime.strptime(d, '%Y-%m-%d').date() for d in sessions]
    if not dates or dates != sorted(set(dates)):
        raise ValueError('invalid reviewed calendar')
    target = datetime.strptime(signal_day, '%Y-%m-%d').date()
    i = dates.index(target)
    if i + 1 >= len(dates):
        raise ValueError('calendar lacks next session')
    following = dates[i + 1]
    if (target.year, target.month) == (following.year, following.month):
        raise ValueError('not a reviewed month-end')
    return following.isoformat()


def build_event(root, bundle, freeze, now):
    review = deepcopy(bundle['review'])
    validate_source_timing(review, now)
    if review.get('status') != 'REVIEWED':
        raise ValueError('review incomplete')
    sources = review['source_sha256']
    def read(name, kind):
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or name not in sources:
            raise ValueError('unbound or external input')
        raw = path.read_bytes()
        if sha256(raw).hexdigest() != sources[name] or review['source_provenance'][name]['kind'] != kind:
            raise ValueError('changed input or wrong evidence kind')
        return raw
    spec = load_spec(root / 'research/hypotheses/0004-cn-etf-dual-momentum/spec.json')
    if set(bundle['prices']) != set(spec.symbols):
        raise ValueError('incomplete price universe')
    frames = {}
    from io import BytesIO
    for s, name in bundle['prices'].items():
        frame = pd.read_csv(BytesIO(read(name, 'market_data')), parse_dates=['date'])
        if frame.date.duplicated().any() or not frame.date.is_monotonic_increasing:
            raise ValueError('duplicate/unsorted prices')
        frames[s] = frame.set_index('date')['close']
    calendar = json.loads(read(bundle['calendar'], 'calendar'))
    action_data = json.loads(read(bundle['actions'], 'corporate_action'))
    day = bundle['signal_day']
    following = month_end_pair(calendar['sessions'], day)
    panel = pd.concat(frames, axis=1)
    if any(str(f.index[-1].date()) != day for f in frames.values()):
        raise ValueError('prices do not all end on signal day')
    expected_dates = [d for d in calendar['sessions'] if str(panel.index[0].date()) <= d <= day]
    if [str(d.date()) for d in panel.index] != expected_dates:
        raise ValueError('price calendar has missing or unexpected sessions')
    if action_data['status'] != 'REVIEWED' or action_data['coverage_start'] > expected_dates[0] or action_data['coverage_end'] < day:
        raise ValueError('corporate action coverage incomplete')
    actions, seen = [], set()
    for a in action_data['actions']:
        key = (a['symbol'], a['date'])
        if key in seen or a['symbol'] not in spec.symbols:
            raise ValueError('duplicate or unknown action')
        seen.add(key)
        actions.append(Action(**{**a, 'date': pd.Timestamp(a['date']),
            'payment_date': pd.Timestamp(a['payment_date']) if a['payment_date'] else None}))
    weights = frozen_weights(panel, actions, spec, day)['weights']
    bound = {'prices': {s: sources[n] for s, n in bundle['prices'].items()},
             'actions': sources[bundle['actions']], 'calendar': sources[bundle['calendar']]}
    review.update(kind='SIGNAL_INPUTS_AND_CALENDAR', signal_day=day, next_session=following,
                  actions_covered_through=action_data['coverage_end'], prices_through=day,
                  input_sha256=digest(bound))
    zone = timezone(timedelta(hours=8))
    def at(d, hour, minute=0):
        return datetime.fromisoformat(d).replace(hour=hour, minute=minute, tzinfo=zone).isoformat()
    signal = {'signal_close_at': at(day, 15), 'execution_not_before': at(following, 9, 30),
              'execution_expires_at': at(following, 10), 'weights': weights,
              'review_status': 'VERIFIED_CALENDAR_ACTIONS_AND_DATA',
              'input_sha256': digest(bound), 'review_evidence_sha256': digest(review)}
    admit_signal(signal, freeze, now)
    return {'kind': 'PRESAVE_SIGNAL', 'signal': signal, 'review': review, 'review_sha256': digest(review)}
