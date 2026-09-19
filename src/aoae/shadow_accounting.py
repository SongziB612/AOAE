"""Deterministic daily shadow accounting; modeled fills are never broker fills.

Inputs must be reviewed upstream. This engine does not establish that supplied
quotes, corporate actions, or calendars are true. No network or order adapter.
"""
from copy import deepcopy
from datetime import date
from decimal import Decimal, ROUND_FLOOR, ROUND_CEILING


def dec(value):
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError('nonfinite amount')
    return result


def new_account(initial=300000, pause_loss=100000):
    if dec(initial) <= 0 or not 0 < dec(pause_loss) <= dec(initial):
        raise ValueError('invalid initial capital/pause')
    return {'cash': str(dec(initial)), 'initial': str(dec(initial)),
            'pause_loss': str(dec(pause_loss)), 'positions': {}, 'receivables': [],
            'action_ids': [], 'last_date': None, 'paused': False, 'equity': str(dec(initial)),
            'peak_equity': str(dec(initial)), 'max_drawdown': '0', 'cost': '0',
            'fills': 0, 'capital_authorized': False}


def advance_day(account, day, previous_day, opens, closes, previous_close,
                actions=(), targets=None, commission='.003', slippage_bps=30,
                fill_fraction='1'):
    """Ex-date entitlements precede trades; cash arrives only on payment date.

    Targets are prior-close weights, not next-open optimized weights. Commission
    floor is 5 CNY; slippage is an explicit cost, as in the frozen replay. Partial
    buys are an assumption, not observed liquidity. A pause means an attempted
    next-session exit, never a guaranteed stop price or maximum loss.
    """
    date.fromisoformat(day)
    date.fromisoformat(previous_day)
    if previous_day >= day or (account['last_date'] and account['last_date'] != previous_day):
        raise ValueError('out-of-order or skipped session')
    universe = set(opens)
    if not universe or set(closes) != universe or set(previous_close) != universe:
        raise ValueError('incomplete prices')
    if set(account['positions']) - universe:
        raise ValueError('unpriced position')
    op, cl, prev = ({s: dec(v) for s, v in p.items()} for p in (opens, closes, previous_close))
    if any(v <= 0 for p in (op, cl, prev) for v in p.values()):
        raise ValueError('nonpositive price')
    rate, slip, fraction = dec(commission), dec(slippage_bps) / 10000, dec(fill_fraction)
    if rate < 0 or slip < 0 or not 0 <= fraction <= 1:
        raise ValueError('invalid costs/fill fraction')
    out = deepcopy(account)
    cash = dec(out['cash'])
    positions = out['positions']
    action_symbols = set()
    for a in actions:
        if a['date'] != day or a['symbol'] not in universe or a['id'] in out['action_ids']:
            raise ValueError('wrong-day, unknown or duplicate action')
        s = a['symbol']
        if s in action_symbols:
            raise ValueError('multiple same-symbol actions require explicit consolidation')
        action_symbols.add(s)
        ratio, dividend = dec(a['ratio']), dec(a['cash_per_old_share'])
        if ratio <= 0 or dividend < 0 or (ratio != 1 and dividend != 0):
            raise ValueError('invalid/ambiguous split and dividend')
        if a['rounding'] not in ('floor', 'ceil'):
            raise ValueError('unknown share rounding')
        if dividend:
            date.fromisoformat(a['payment_date'])
            if a['payment_date'] < day:
                raise ValueError('payment before entitlement')
        old = positions.get(s, 0)
        if type(old) is not int or old < 0:
            raise ValueError('invalid position')
        if old and dividend:
            out['receivables'].append({'due': a['payment_date'], 'amount': str(old * dividend), 'action_id': a['id']})
        positions[s] = int((old * ratio).to_integral_value(rounding=ROUND_FLOOR if a['rounding'] == 'floor' else ROUND_CEILING))
        prev[s] = (prev[s] - dividend) / ratio
        if prev[s] <= 0:
            raise ValueError('invalid action-adjusted reference')
        out['action_ids'].append(a['id'])
    cash += sum((dec(r['amount']) for r in out['receivables'] if r['due'] <= day), Decimal(0))
    out['receivables'] = [r for r in out['receivables'] if r['due'] > day]
    receivable = sum((dec(r['amount']) for r in out['receivables']), Decimal(0))
    pre_equity = cash + receivable + sum((q * prev[s] for s, q in positions.items()), Decimal(0))
    if out['paused']:
        targets = {s: 0 for s in universe}
    draft = None
    if targets is not None:
        if set(targets) != universe:
            raise ValueError('incomplete target universe')
        weights = {s: dec(v) for s, v in targets.items()}
        # Float-generated covariance weights may sum to 1 + machine epsilon.
        # Permit representation noise only; cash funding still forbids leverage.
        if any(v < 0 for v in weights.values()) or sum(weights.values()) > Decimal('1.000000000001'):
            raise ValueError('leveraged or negative target')
        draft = {s: int((pre_equity * w / prev[s] / 100).to_integral_value(rounding=ROUND_FLOOR)) * 100 for s, w in weights.items()}
    trades = []
    total_cost = Decimal(0)
    def cost(count, symbol):
        notional = count * op[symbol]
        return max(Decimal(5), notional * rate) + notional * slip
    if draft is not None:
        for side in ('SELL', 'BUY'):
            # Stable universe order is frozen by caller dict order, not set order.
            for s in opens:
                held = positions.get(s, 0)
                delta = draft[s] - held
                if (side == 'SELL' and delta >= 0) or (side == 'BUY' and delta <= 0):
                    continue
                q = abs(delta)
                if side == 'BUY':
                    q = int((q * fraction / 100).to_integral_value(rounding=ROUND_FLOOR)) * 100
                    while q and q * op[s] + cost(q, s) > cash:
                        q -= 100
                if not q:
                    continue
                fee = cost(q, s)
                cash += q * op[s] - fee if side == 'SELL' else -q * op[s] - fee
                if cash < 0:
                    raise ValueError('unfunded fees')
                positions[s] = held - q if side == 'SELL' else held + q
                total_cost += fee
                trades.append({'kind': 'MODELED_FILL_NOT_OBSERVED', 'date': day, 'symbol': s,
                               'side': side, 'quantity': q, 'price': str(op[s]), 'cost': str(fee)})
    equity = cash + receivable + sum((q * cl[s] for s, q in positions.items()), Decimal(0))
    peak = max(dec(out['peak_equity']), equity)
    out.update(cash=str(cash), equity=str(equity), peak_equity=str(peak),
               max_drawdown=str(min(dec(out['max_drawdown']), equity / peak - 1)),
               cost=str(dec(out['cost']) + total_cost), last_date=day,
               fills=out['fills'] + len(trades),
               paused=out['paused'] or equity <= dec(out['initial']) - dec(out['pause_loss']))
    return out, trades
