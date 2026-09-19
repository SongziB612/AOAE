"""Three-arm event reducer for an isolated engineering shadow ledger.

Review documents are assertions whose truth requires external verification.
Never attach this reducer to the legacy cash journal or call it live execution.
"""
from copy import deepcopy
from datetime import timedelta, timezone

from aoae.forward_journal import digest
from aoae.paired_forward import admit_signal, timestamp
from aoae.shadow_accounting import advance_day, new_account


def review(event, at, kind):
    evidence = event['review']
    if event['review_sha256'] != digest(evidence):
        raise ValueError('review digest mismatch')
    if evidence['kind'] != kind or evidence['status'] != 'REVIEWED' or not evidence.get('source_sha256'):
        raise ValueError('missing review evidence')
    if timestamp(evidence['reviewed_at']) > timestamp(at):
        raise ValueError('future review')
    return evidence


def reduce_shadow(state, event, recorded_at):
    state = deepcopy(state)
    if event['kind'] == 'SHADOW_INIT':
        if state is not None:
            raise ValueError('already initialized')
        freeze = event['freeze']
        for key in ('capital_authorized', 'orders_authorized', 'broker_connection_authorized'):
            if freeze.get(key) is not False:
                raise ValueError('simulation-only freeze required')
        return {'freeze': freeze, 'accounts': {a: new_account(freeze['initial_paper_capital_per_arm_cny'], freeze['risk_pause_loss_cny']) for a in freeze['arms']},
                'last_date': None, 'pending_signal': None, 'signals': [], 'daily': [],
                'status': 'ENGINEERING_SHADOW_NOT_CAPITAL_EVIDENCE', 'capital_authorized': False}
    if state is None:
        raise ValueError('missing genesis')
    if event['kind'] == 'PRESAVE_SIGNAL':
        evidence = review(event, recorded_at, 'SIGNAL_INPUTS_AND_CALENDAR')
        raw = event['signal']
        close = timestamp(raw['signal_close_at'])
        execution = timestamp(raw['execution_not_before'])
        shanghai = timezone(timedelta(hours=8))
        day, next_day = close.astimezone(shanghai).date().isoformat(), execution.astimezone(shanghai).date().isoformat()
        if evidence['signal_day'] != day or evidence['next_session'] != next_day or day[:7] == next_day[:7]:
            raise ValueError('not reviewed month-end/next-session pair')
        if evidence['actions_covered_through'] < day or evidence['prices_through'] != day:
            raise ValueError('incomplete action/price coverage')
        if raw['review_evidence_sha256'] != event['review_sha256']:
            raise ValueError('signal not bound to review')
        if raw['input_sha256'] != evidence['input_sha256']:
            raise ValueError('signal not bound to input digest')
        if state['pending_signal'] is not None or any(s['day'] == day for s in state['signals']):
            raise ValueError('pending/duplicate signal')
        signal = admit_signal(raw, state['freeze'], recorded_at)
        state['pending_signal'] = signal
        state['signals'].append({'day': day, 'id': signal['signal_id'], 'saved_at': recorded_at})
        return state
    if event['kind'] != 'MODELED_DAY':
        raise ValueError('unsupported event; no live order adapter')
    evidence = review(event, recorded_at, 'DAY_PRICES_AND_ACTIONS')
    day = event['day']
    if evidence['day'] != day or evidence['previous_session'] != event['previous_day']:
        raise ValueError('day/session mismatch')
    if evidence['input_sha256'] != digest(event['inputs']):
        raise ValueError('prices/actions not bound to review')
    close = timestamp(event['close_at'])
    opening = timestamp(event['open_at'])
    shanghai = timezone(timedelta(hours=8))
    if not opening < close <= timestamp(recorded_at) or opening.astimezone(shanghai).date().isoformat() != day or close.astimezone(shanghai).date().isoformat() != day:
        raise ValueError('invalid daily timing')
    signal = state['pending_signal']
    targets = None
    signal_outcome = 'NO_SIGNAL'
    if signal:
        start, expiry = timestamp(signal['execution_not_before']), timestamp(signal['execution_expires_at'])
        if start <= opening < expiry:
            if timestamp(signal['captured_at_utc']) >= opening:
                raise ValueError('late signal')
            if timestamp(signal['signal_close_at']).astimezone(shanghai).date().isoformat() != event['previous_day']:
                raise ValueError('signal is not previous-session close')
            targets = signal['weights']
            signal_outcome = 'MODELED_NOT_OBSERVED'
            state['pending_signal'] = None
        elif opening >= expiry:
            signal_outcome = 'MISSED_NOT_BACKFILLED'
            state['pending_signal'] = None
    trades = {}
    opens = event['inputs']['opens']
    if 'execution_order' in event['inputs']:
        order = event['inputs']['execution_order']
        if len(order) != len(opens) or set(order) != set(opens):
            raise ValueError('invalid explicit execution order')
        opens = {s: opens[s] for s in order}
    for arm, account in state['accounts'].items():
        updated, fills = advance_day(account, day, event['previous_day'],
                                     opens, event['inputs']['closes'], event['inputs']['previous_close'],
                                     event['inputs']['actions'], None if targets is None else targets[arm])
        state['accounts'][arm] = updated
        trades[arm] = fills
    state['last_date'] = day
    state['daily'].append({'day': day, 'signal_outcome': signal_outcome, 'fills': trades,
                           'equity': {a: v['equity'] for a, v in state['accounts'].items()},
                           'observed_broker_fills': 0})
    return state
