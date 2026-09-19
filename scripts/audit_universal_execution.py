"""Independent Decimal reconstruction of execution scenario ledgers.

No production engine, pandas/numpy, strategy or fee-helper imports.
"""
from decimal import Decimal


def audit(record):
    def dec(value):
        result = Decimal(str(value))
        if not result.is_finite():
            raise ValueError('nonfinite ledger number')
        return result

    days, symbols = record['dates'], record['symbols']
    settings, observed = record['settings'], record['result']
    if days != sorted(set(days)) or not days or len(observed['rows']) != len(days):
        raise ValueError('invalid audit calendar')
    cash, initial = dec(settings['initial']), dec(settings['initial'])
    positions = {s: 0 for s in symbols}
    pending, events, trades = [], {}, {}
    for action in record['actions']:
        events.setdefault(action['ex_date'], []).append(action)
    for order in observed['orders']:
        if order['date'] not in days[1:]:
            raise ValueError('order outside eligible sessions')
        trades.setdefault(order['date'], []).append(order)
    worst_error, paused = Decimal(0), False
    for i, day in enumerate(days):
        for action in events.get(day, []):
            if not action['known_date'] < day <= action['payment_date']:
                raise ValueError('invalid action timing')
            due = next((j for j, d in enumerate(days) if d >= action['payment_date']), len(days))
            pending.append((due, positions[action['symbol']] * dec(action['cash_per_share'])))
        cash += sum((amount for due, amount in pending if due <= i), Decimal(0))
        pending = [(due, amount) for due, amount in pending if due > i]
        used_capacity = {s: 0 for s in symbols}
        for order in trades.get(day, []):
            count, symbol = order['quantity'], order['symbol']
            if type(count) is not int or count <= 0 or symbol not in positions or order['signal_date'] != days[i - 1]:
                raise ValueError('invalid order or signal timing')
            side = {'BUY': 1, 'SELL': -1}[order['side']]
            if bool(order['paused_liquidation']) != paused or (paused and side == 1):
                raise ValueError('pause policy violation')
            used_capacity[symbol] += count
            if dec(used_capacity[symbol]) > dec(record['opening_capacity'][i][symbol]):
                raise ValueError('opening capacity exceeded')
            price = dec(record['opens'][i][symbol]) * (1 + side * dec(settings['adverse_bps']) / 10000)
            fee = max(dec(settings['minimum_fee']), price * count * dec(settings['commission_bps']) / 10000)
            if abs(price - dec(order['price'])) > Decimal('1e-9') or abs(fee - dec(order['fee'])) > Decimal('1e-7'):
                raise ValueError('price/fee mismatch')
            cash -= fee
            if side == 1:
                cash -= price * count
            elif settings['settlement_sessions'] == 0:
                cash += price * count
            else:
                pending.append((i + settings['settlement_sessions'], price * count))
            positions[symbol] += side * count
            if cash < Decimal('-1e-7') or min(positions.values()) < 0:
                raise ValueError('unfunded order')
        receivables = sum((v for _, v in pending), Decimal(0))
        equity = cash + receivables + sum(positions[s] * dec(record['closes'][i][s]) for s in symbols)
        paused = paused or equity <= initial - dec(settings['pause_loss'])
        row = observed['rows'][i]
        if row['date'] != day or row['positions'] != positions or bool(row['paused']) != paused:
            raise ValueError('state mismatch')
        for key, expected in [('cash', cash), ('receivable', receivables), ('equity', equity)]:
            error = abs(dec(row[key]) - expected)
            worst_error = max(worst_error, error)
            if error > Decimal('0.000001'):
                raise ValueError('ledger mismatch: ' + key)
    return {'status': 'PASS', 'sessions': len(days), 'orders': len(observed['orders']),
            'maximum_absolute_error': float(worst_error), 'capital_authorized': False,
            'scope': 'Independent cash, receivables, holdings, price, fee, capacity and pause reconstruction; not validation of target optimality, real fills or data truth.'}
