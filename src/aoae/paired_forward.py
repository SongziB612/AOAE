"""Isolated forward evidence admission and simulated three-arm cash ledgers."""
from copy import deepcopy
from datetime import date, datetime
from hashlib import sha256
import json
import math


def timestamp(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError('timezone-aware timestamp required')
    return result


def initial_accounts(freeze):
    return {arm: {'cash_cny': float(freeze['initial_paper_capital_per_arm_cny']),
                  'positions': {}, 'simulated_fills': 0} for arm in freeze['arms']}


def freshness(records, expected_market_date):
    if not records:
        raise ValueError('empty market snapshot')
    dates = {row['last_market_date'] for row in records.values()}
    date.fromisoformat(expected_market_date)
    for value in dates:
        date.fromisoformat(value)
    if len(dates) != 1:
        return 'BLOCKED_ASSET_DATE_MISMATCH'
    observed = next(iter(dates))
    if observed > expected_market_date:
        return 'BLOCKED_FUTURE_MARKET_DATE'
    return 'CURRENT' if observed == expected_market_date else 'BLOCKED_STALE_MARKET_DATA'


def admit_signal(signal, freeze, captured_at):
    """Timing/shape validation, not certification of calendar/action reviewers."""
    captured = timestamp(captured_at)
    close = timestamp(signal['signal_close_at'])
    execution = timestamp(signal['execution_not_before'])
    if timestamp(signal['execution_expires_at']) <= execution:
        raise ValueError('invalid execution window')
    if not timestamp(freeze['frozen_at_utc']) < close <= captured < execution:
        raise ValueError('late, backfilled or pre-freeze signal')
    if signal.get('review_status') != 'VERIFIED_CALENDAR_ACTIONS_AND_DATA':
        raise ValueError('signal data/calendar/actions not reviewed')
    for name in ('review_evidence_sha256', 'input_sha256'):
        value = signal.get(name)
        if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError('invalid review/input evidence digest')
    if set(signal['weights']) != set(freeze['arms']):
        raise ValueError('arms differ from freeze')
    for weights in signal['weights'].values():
        if not weights or any(not math.isfinite(v) or v < 0 for v in weights.values()) or sum(weights.values()) > 1 + 1e-10:
            raise ValueError('invalid unlevered weights')
    result = deepcopy(signal)
    result['captured_at_utc'] = captured_at
    result['signal_id'] = sha256(json.dumps(result, sort_keys=True, allow_nan=False).encode()).hexdigest()
    result['capital_authorized'] = False
    return result


def apply_simulated_fill(accounts, signal, fill, recorded_at):
    """Explicit simulations only. No broker fill represented as observed here.

    This ledger handles cash trades only; corporate actions and mark-to-market
    must be separately admitted. It is not a complete execution simulator.
    """
    if fill.get('kind') != 'SIMULATED_FILL' or fill.get('signal_id') != signal.get('signal_id'):
        raise ValueError('unbound or non-simulated fill')
    when = timestamp(fill['execution_at'])
    if not timestamp(signal['captured_at_utc']) < when <= timestamp(recorded_at):
        raise ValueError('invalid fill timing')
    if not timestamp(signal['execution_not_before']) <= when < timestamp(signal['execution_expires_at']):
        raise ValueError('outside execution window')
    arm, symbol = fill['arm'], fill['symbol']
    if arm not in accounts or symbol not in signal['weights'][arm]:
        raise ValueError('unknown arm or symbol')
    count, price, cost = fill['quantity'], fill['price'], fill['cost_cny']
    if type(count) is not int or count <= 0 or not all(math.isfinite(x) and x > 0 for x in (price, cost)):
        raise ValueError('invalid size/price/cost')
    result = deepcopy(accounts)
    ledger = result[arm]
    seen = ledger.setdefault('fill_ids', [])
    if not fill.get('fill_id') or fill['fill_id'] in seen:
        raise ValueError('duplicate or missing fill id')
    held = ledger['positions'].get(symbol, 0)
    if fill['side'] == 'BUY':
        if count % 100 or count * price + cost > ledger['cash_cny']:
            raise ValueError('invalid lot or unfunded purchase')
        ledger['cash_cny'] -= count * price + cost
        ledger['positions'][symbol] = held + count
    elif fill['side'] == 'SELL':
        if count > held or ledger['cash_cny'] + count * price < cost:
            raise ValueError('uncovered/unfunded sale')
        ledger['cash_cny'] += count * price - cost
        ledger['positions'][symbol] = held - count
    else:
        raise ValueError('invalid side')
    ledger['simulated_fills'] += 1
    seen.append(fill['fill_id'])
    return result
