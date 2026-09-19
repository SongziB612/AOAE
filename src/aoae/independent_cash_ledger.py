"""Independent Decimal ledger; no strategy/simulator imports or fee helpers."""
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR


def verify_ledger(dates, closes, orders, actions, initial, rate, slippage_bps):
    def dec(value):
        result = Decimal(str(value))
        if not result.is_finite():
            raise ValueError('nonfinite ledger input')
        return result

    cash = dec(initial)
    holdings = {s: 0 for s in closes[dates[0]]}
    by_day, action_days = {}, {}
    for order in orders:
        if order['date'] not in dates:
            raise ValueError('order outside ledger calendar')
        by_day.setdefault(order['date'], []).append(order)
    for action in actions:
        action_days.setdefault(action['date'], []).append(action)
    pending, values = [], []
    for date in dates:
        for action in action_days.get(date, []):
            symbol = action['symbol']
            if symbol not in holdings:
                continue
            old = holdings[symbol]
            dividend = old * dec(action['cash_per_old_share'])
            if dividend:
                payment = action['payment_date']
                if not payment or payment < date:
                    raise ValueError('invalid payment date')
                pending.append((payment, dividend))
            rounding = {'floor': ROUND_FLOOR, 'ceil': ROUND_CEILING}[action['rounding']]
            holdings[symbol] = int((old * dec(action['ratio'])).to_integral_value(rounding=rounding))
        cash += sum((value for payment, value in pending if payment <= date), Decimal(0))
        pending = [(payment, value) for payment, value in pending if payment > date]
        for order in by_day.get(date, []):
            count, symbol = order['quantity'], order['symbol']
            if type(count) is not int or count <= 0 or symbol not in holdings:
                raise ValueError('invalid quantity or symbol')
            notional = count * dec(order['price'])
            if notional <= 0:
                raise ValueError('nonpositive price')
            fee = max(Decimal(5), notional * dec(rate)) + notional * dec(slippage_bps) / 10000
            if abs(fee - dec(order['cost'])) > Decimal('0.000001'):
                raise ValueError('fee disagrees with independent formula')
            if order['side'] == 'BUY':
                if count % 100:
                    raise ValueError('buy is not a full lot')
                holdings[symbol] += count
                cash -= notional + fee
            elif order['side'] == 'SELL':
                if count > holdings[symbol]:
                    raise ValueError('uncovered sale')
                holdings[symbol] -= count
                cash += notional - fee
            else:
                raise ValueError('unknown side')
            if cash < Decimal('-0.000001'):
                raise ValueError('unfunded buy or fee')
        value = cash + sum((v for _, v in pending), Decimal(0))
        value += sum((q * dec(closes[date][s]) for s, q in holdings.items()), Decimal(0))
        values.append(float(value))
    return values
