"""Next-open, whole-share research replay; not broker fills or live execution.

Input opening capacities are explicit scenario/observed bounds, never inferred
from that day's closing volume. Caller must independently admit input data.
"""
from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

from aoae.universal import simplex, universal_weights


@dataclass(frozen=True)
class CashAction:
    symbol: str
    ex_date: str
    known_date: str
    payment_date: str
    cash_per_share: float


def replay_next_open(opens, closes, opening_capacity, targets, actions=(), *,
                     initial=10000., commission_bps=5., minimum_fee=1.,
                     adverse_bps=10., settlement_sessions=1, pause_loss=1000.):
    """Prior-close targets, explicit cash/receivables, sell-before-buy.

    Cash dividends only: splits must be handled by a separately validated layer,
    never silently applied again to split-adjusted OHLC. No borrowing or FX.
    Sell proceeds are unavailable until settlement. Fee charged immediately.
    Unknown/late dividend announcements fail closed. USD-like abstract units;
    fees/taxes are configured scenarios, not certified broker schedules.
    """
    assets = list(closes.columns)
    if not assets or closes.empty or len(closes) < 2 or closes.columns.has_duplicates:
        raise ValueError('empty/duplicate asset input')
    if not closes.index.is_unique or not closes.index.is_monotonic_increasing:
        raise ValueError('invalid session ordering')
    for frame in (opens, closes, opening_capacity):
        if not frame.index.equals(closes.index) or not frame.columns.equals(closes.columns):
            raise ValueError('calendar/assets not aligned')
        if not np.isfinite(frame.to_numpy(dtype=float)).all():
            raise ValueError('nonfinite input')
    if (opens <= 0).any().any() or (closes <= 0).any().any() or (opening_capacity < 0).any().any():
        raise ValueError('invalid prices or capacity')
    if not all(math.isfinite(v) and v > 0 for v in (initial, commission_bps, minimum_fee, adverse_bps, pause_loss)):
        raise ValueError('positive finite capital, costs and loss budget required')
    if adverse_bps >= 10000 or pause_loss >= initial or type(settlement_sessions) is not int or settlement_sessions < 0:
        raise ValueError('invalid settlement, loss budget or slippage')
    days = [str(pd.Timestamp(d).date()) for d in closes.index]
    if len(days) != len(set(days)):
        raise ValueError('multiple bars per session unsupported')
    for day, target in targets.items():
        if day not in days[1:]:
            raise ValueError('target needs a preceding session')
        simplex([target.get(s, 0.) for s in assets], len(assets))
        if set(target) - set(assets):
            raise ValueError('unknown target asset')
    events, seen = {}, set()
    for action in actions:
        for day in (action.ex_date, action.known_date, action.payment_date):
            if str(pd.Timestamp(day).date()) != day:
                raise ValueError('noncanonical action date')
        key = action.symbol, action.ex_date
        if (key in seen or action.symbol not in assets or action.ex_date not in days or
            action.known_date >= action.ex_date or action.payment_date < action.ex_date or
            not math.isfinite(action.cash_per_share) or action.cash_per_share <= 0):
            raise ValueError('invalid/duplicate/late action')
        seen.add(key)
        events.setdefault(action.ex_date, []).append(action)
    quantities = {s: 0 for s in assets}
    cash, pending, rows, orders, paused = initial, [], [], [], False
    for i, day in enumerate(days):
        for action in events.get(day, []):
            # Purchases on ex-date do not receive the dividend.
            entitlement = quantities[action.symbol] * action.cash_per_share
            if entitlement:
                due = int(np.searchsorted(days, action.payment_date))
                pending.append((due, entitlement))
        cash += sum(amount for due, amount in pending if due <= i)
        pending = [(due, amount) for due, amount in pending if due > i]
        goal = None
        if i and (paused or day in targets):
            reference = closes.iloc[i - 1].to_dict()
            for action in events.get(day, []):
                reference[action.symbol] -= action.cash_per_share
            if min(reference.values()) <= 0:
                raise ValueError('cash action incompatible with reference price')
            equity_before = cash + sum(a for _, a in pending) + sum(quantities[s] * reference[s] for s in assets)
            goal = {s: 0 if paused else math.floor(equity_before * targets[day].get(s, 0.) / reference[s]) for s in assets}
        if goal is not None:
            for side in (-1, 1):
                for s in assets:
                    delta = goal[s] - quantities[s]
                    if delta * side <= 0:
                        continue
                    count = min(abs(delta), math.floor(float(opening_capacity.iloc[i][s])))
                    price = float(opens.iloc[i][s]) * (1 + side * adverse_bps / 10000)
                    if side == 1:
                        count = min(count, max(0, math.floor(cash / (price * (1 + commission_bps / 10000)))))
                    while count:
                        notional = count * price
                        fee = max(minimum_fee, notional * commission_bps / 10000)
                        if (notional + fee if side == 1 else fee) <= cash + 1e-10:
                            break
                        count -= 1
                    if not count:
                        continue
                    quantities[s] += side * count
                    cash -= fee
                    if side == 1:
                        cash -= notional
                    elif settlement_sessions == 0:
                        cash += notional
                    else:
                        pending.append((i + settlement_sessions, notional))
                    orders.append({'date': day, 'signal_date': days[i - 1], 'symbol': s,
                                   'side': 'BUY' if side == 1 else 'SELL', 'quantity': count,
                                   'price': price, 'fee': fee, 'paused_liquidation': paused})
        if cash < -1e-7 or min(quantities.values()) < 0:
            raise ValueError('unfunded account')
        receivable = sum(a for _, a in pending)
        value = cash + receivable + sum(quantities[s] * float(closes.iloc[i][s]) for s in assets)
        paused = paused or value <= initial - pause_loss
        rows.append({'date': day, 'cash': cash, 'receivable': receivable,
                     'positions': quantities.copy(), 'equity': value, 'paused': paused})
    return {'rows': rows, 'orders': orders, 'capital_authorized': False,
            'information_class': 'RAW_PRICE_EXECUTION_SCENARIO_NOT_VERIFIED_FILLS',
            'limits': ['No split/FX/withholding/tax support; caller must reject datasets requiring these.',
                       'Opening capacity and adverse fills are assumptions unless independently measured.',
                       'Daily cash dividend publication must precede ex-date; intraday announcements unsupported.',
                       'Cash-account settlement delay is configured, not inferred from exchange rules.',
                       'Loss threshold triggers next-session attempts; gaps/capacity may exceed loss budget.']}


def gross_up_next_open_targets(total_return_close, experts):
    """Index must be forward-built from admitted actions, not vendor adj-close.

    At open t, expert scores contain close-to-close returns only through t-1.
    The costless expert identity is NOT an identity of this actual fill account.
    """
    values = total_return_close.to_numpy(dtype=float)
    if len(values) < 2 or not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError('invalid forward total return index')
    weights, _ = universal_weights(values[1:] / values[:-1], experts)
    return {str(pd.Timestamp(day).date()): dict(zip(total_return_close.columns, row, strict=True))
            for day, row in zip(total_return_close.index[1:], weights, strict=True)}
