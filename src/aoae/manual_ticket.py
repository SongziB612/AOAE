"""Paper-only manual execution tickets; no broker client or capital authority."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from hashlib import sha256
import json

from aoae.paired_forward import admit_signal, timestamp


def number(value):
    result = Decimal(str(value))
    if not result.is_finite() or result < 0:
        raise ValueError('nonfinite or negative number')
    return result


def count(value):
    result = number(value)
    if result != result.to_integral_value():
        raise ValueError('fractional quantity')
    return int(result)


def seal(value):
    return sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def prepare(request, now):
    """Sizes from current snapshots, never from a future/historical open fill.

    Input review flags are not independently certified here. Every output remains
    rehearsal-only. Sells do not fund buys until a new reconciled account is used.
    """
    when = timestamp(now)
    result = {'schema_version': 1, 'created_at': now, 'status': 'WAIT_NO_SIGNAL',
              'classification': 'PAPER_REHEARSAL_ONLY_NOT_A_LIVE_ORDER',
              'orders_authorized': False, 'capital_authorized': False,
              'broker_connection_authorized': False, 'legs': [],
              'request_sha256': seal(request)}
    if request.get('signal') is None:
        result['reason'] = 'No supplied admitted signal; never infer a trade from an old backtest.'
        result['ticket_id'] = seal(result)
        return result
    signal = admit_signal(request['signal'], request['freeze'], request['captured_at'])
    start, end = timestamp(signal['execution_not_before']), timestamp(signal['execution_expires_at'])
    if not start <= when < end:
        raise ValueError('outside signal execution window')
    weights = {s: number(w) for s, w in signal['weights'][request['arm']].items()}
    account, quotes = request['account'], request['quotes']
    if not 0 <= (when - timestamp(account['as_of'])).total_seconds() <= 60:
        raise ValueError('stale/future account snapshot')
    if account.get('open_orders') != []:
        raise ValueError('outstanding orders must be reconciled first')
    if set(quotes) != set(weights) or set(account['positions']) - set(weights):
        raise ValueError('universe mismatch; include existing holdings')
    positions = {s: count(account['positions'].get(s, 0)) for s in weights}
    available = {s: count(account['available_to_sell'].get(s, 0)) for s in weights}
    cash = number(account['available_cash_cny'])
    if any(available[s] > positions[s] for s in weights):
        raise ValueError('available shares exceed holdings')
    expiry = min(end, when + timedelta(seconds=60))
    for s, q in quotes.items():
        observed = timestamp(q['as_of'])
        if not 0 <= (when - observed).total_seconds() < 60 or q.get('tradable') is not True:
            raise ValueError('stale/future quote or unverified tradability')
        bid, ask, tick = (number(q[k]) for k in ('bid', 'ask', 'tick_size'))
        if not 0 < bid <= ask or tick <= 0 or bid % tick or ask % tick:
            raise ValueError('invalid quote/tick')
        expiry = min(expiry, observed + timedelta(seconds=60))
    fee = request['fees']
    rate, minimum = number(fee['commission_rate']), number(fee['minimum_cny'])
    if rate > Decimal('.01') or not fee.get('basis'):
        raise ValueError('invalid or undocumented fee assumption')
    equity = cash + sum(positions[s] * number(quotes[s]['bid']) for s in weights)
    if equity <= 0:
        raise ValueError('empty account')
    legs, blocked = [], []
    for s in sorted(weights):
        target = int(equity * weights[s] / number(quotes[s]['ask']) / 100) * 100
        delta = target - positions[s]
        if not delta:
            continue
        side = 'BUY' if delta > 0 else 'SELL'
        quantity = abs(delta)
        if side == 'BUY':
            quantity = quantity // 100 * 100
        elif quantity > available[s]:
            blocked.append(s + ': insufficient available-to-sell shares')
            continue
        if not quantity:
            continue
        price = number(quotes[s]['ask' if side == 'BUY' else 'bid'])
        cost = max(minimum, quantity * price * rate)
        legs.append({'symbol': s, 'side': side, 'quantity': quantity,
                     'limit_price': str(price), 'estimated_commission_cny': str(cost),
                     'reference_quote_at': quotes[s]['as_of'], 'reference_price': str(price)})
    buy_cash = sum(number(l['limit_price']) * l['quantity'] + number(l['estimated_commission_cny'])
                   for l in legs if l['side'] == 'BUY')
    # Do not silently change the strategy or assume that pending sales filled.
    if buy_cash > cash:
        blocked.append('insufficient settled available cash including fees; reconcile sales and regenerate')
    if blocked:
        legs = []
    result.update(status='BLOCKED' if blocked else ('PAPER_REVIEW_READY' if legs else 'NO_REBALANCE'),
                  signal_id=signal['signal_id'], arm=request['arm'], expires_at=expiry.isoformat(),
                  execution_not_before=signal['execution_not_before'], blockers=blocked,
                  legs=sorted(legs, key=lambda l: (l['side'] != 'SELL', l['symbol'])),
                  initial_positions=positions, initial_available_to_sell=available,
                  initial_available_cash_cny=str(cash), fees=deepcopy(fee),
                  seconds_after_model_open=(when-start).total_seconds(),
                  delay_backtest_validated=False,
                  cancellation_rule='At expiry request cancellation; verify final order status before any replacement.',
                  warnings=['Prices and tradability are supplied snapshots, not a verified live feed.',
                            'No automatic cancellation, follow-up, real-money approval or profitability claim.',
                            'Manual fills must not be booked as historical opening fills.'])
    result['ticket_id'] = seal(result)
    return result


def reconcile(ticket, fills, now):
    """Audit normalized CSV rows. Imported reports are not broker-authenticated."""
    body = {k: v for k, v in ticket.items() if k != 'ticket_id'}
    if seal(body) != ticket.get('ticket_id') or ticket['status'] != 'PAPER_REVIEW_READY':
        raise ValueError('changed ticket or no reviewable legs')
    when = timestamp(now)
    allowed = {(l['symbol'], l['side']): l for l in ticket['legs']}
    totals = dict.fromkeys(allowed, 0)
    cash = number(ticket['initial_available_cash_cny'])
    positions = dict(ticket['initial_positions'])
    available = dict(ticket['initial_available_to_sell'])
    seen, violations, details = set(), [], []
    fees = Decimal(0)
    last = None
    for row in fills:
        try:
            ident = row['fill_id']
            at = timestamp(row['execution_at'])
            key = (row['symbol'], row['side'])
            if not ident or ident in seen:
                raise ValueError('duplicate/missing fill id')
            seen.add(ident)
            if row['ticket_id'] != ticket['ticket_id'] or key not in allowed:
                raise ValueError('unbound fill or wrong symbol/side')
            if last and at < last:
                raise ValueError('fills not in execution order')
            last = at
            if not timestamp(ticket['created_at']) <= at <= when:
                raise ValueError('fill precedes ticket or is in future')
            quantity, price = count(row['quantity']), number(row['price'])
            cost = number(row['commission_cny']) + number(row['other_fees_cny'])
            if quantity <= 0 or price <= 0:
                raise ValueError('zero price/quantity')
            leg = allowed[key]
            if totals[key] + quantity > leg['quantity']:
                raise ValueError('overfill')
            if (key[1] == 'BUY' and price > number(leg['limit_price'])) or (key[1] == 'SELL' and price < number(leg['limit_price'])):
                raise ValueError('limit violation')
            delta = quantity * price
            if key[1] == 'BUY':
                if delta + cost > cash:
                    raise ValueError('unfunded fill')
                cash -= delta + cost
                positions[key[0]] += quantity
            else:
                if quantity > available[key[0]] or cash + delta < cost:
                    raise ValueError('unavailable/unfunded sale')
                cash += delta - cost
                positions[key[0]] -= quantity
                available[key[0]] -= quantity
            totals[key] += quantity
            fees += cost
            if at >= timestamp(ticket['expires_at']):
                violations.append(ident + ': late fill; reconcile cancellation status')
            reference = number(leg['reference_price'])
            details.append({'fill_id': ident, 'adverse_slippage_bps': str((price/reference-1)*10000*(1 if key[1]=='BUY' else -1)),
                            'seconds_after_model_open': (at-timestamp(ticket['execution_not_before'])).total_seconds()})
        except (ValueError, KeyError, ArithmeticError) as exc:
            violations.append(str(exc))
    complete = all(totals[k] == allowed[k]['quantity'] for k in allowed)
    return {'status': 'VIOLATION' if violations else ('COMPLETE_REPORTED' if complete else 'PARTIAL_REPORTED'),
            'ticket_id': ticket['ticket_id'], 'violations': violations, 'details': details,
            'reported_cash_cny': str(cash), 'reported_positions': positions, 'reported_total_fees_cny': str(fees),
            'ledger_valid': not violations, 'broker_authenticated': False,
            'unfilled': {s+':'+side: allowed[(s,side)]['quantity']-q for (s,side),q in totals.items()},
            'follow_up': 'Confirm broker order status; never automatically resubmit missing quantity.',
            'automatic_follow_up_allowed': False, 'capital_authorized': False}
