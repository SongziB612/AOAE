"""Derive daily accounting inputs from reviewed files, never typed prices."""
from copy import deepcopy
import csv
from datetime import date
from hashlib import sha256
from io import StringIO
import json

from aoae.forward_journal import digest
from aoae.shadow_accounting import dec
from aoae.source_timing import validate_source_timing


def build_day(root, bundle, symbols, now):
    review = deepcopy(bundle['review'])
    validate_source_timing(review, now)
    if review.get('status') != 'REVIEWED':
        raise ValueError('review incomplete')

    def read(name, kind):
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError('outside-workspace input')
        raw = path.read_bytes()
        if sha256(raw).hexdigest() != review['source_sha256'].get(name):
            raise ValueError('changed or unbound input')
        if review['source_provenance'][name]['kind'] != kind:
            raise ValueError('wrong source kind')
        return raw

    day = bundle['day']
    date.fromisoformat(day)
    calendar = json.loads(read(bundle['calendar'], 'calendar'))['sessions']
    if not calendar or calendar != sorted(set(calendar)):
        raise ValueError('invalid calendar')
    for value in calendar:
        date.fromisoformat(value)
    index = calendar.index(day)
    if index == 0:
        raise ValueError('missing previous session')
    previous = calendar[index - 1]
    if set(bundle['prices']) != set(symbols):
        raise ValueError('wrong executable universe')
    inputs = {'opens': {}, 'closes': {}, 'previous_close': {}, 'actions': [],
              'execution_order': list(symbols)}
    for symbol in symbols:
        rows = list(csv.DictReader(StringIO(read(bundle['prices'][symbol], 'market_data').decode('utf-8-sig'))))
        days = [row['date'] for row in rows]
        if days != sorted(set(days)) or not days or days[-1] != day or previous not in days:
            raise ValueError('incomplete/duplicate/future daily prices')
        current, prior = rows[-1], rows[days.index(previous)]
        for key, value in [('opens', current['open']), ('closes', current['close']), ('previous_close', prior['close'])]:
            if dec(value) <= 0:
                raise ValueError('invalid daily price')
            inputs[key][symbol] = str(dec(value))
    actions = json.loads(read(bundle['actions'], 'corporate_action'))
    if actions['status'] != 'REVIEWED' or actions['coverage_start'] > day or actions['coverage_end'] < day:
        raise ValueError('incomplete action review')
    seen = set()
    for action in actions['actions']:
        date.fromisoformat(action['date'])
        if action['date'] != day:
            continue
        if action['symbol'] not in symbols:
            raise ValueError('unknown action symbol')
        if action['symbol'] in seen:
            raise ValueError('duplicate daily action')
        seen.add(action['symbol'])
        inputs['actions'].append(action)
    review.update(kind='DAY_PRICES_AND_ACTIONS', day=day, previous_session=previous,
                  input_sha256=digest(inputs))
    return {'kind': 'MODELED_DAY', 'day': day, 'previous_day': previous,
            'open_at': day + 'T09:30:00+08:00', 'close_at': day + 'T15:00:00+08:00',
            'inputs': inputs, 'review': review, 'review_sha256': digest(review)}
