"""Raw-price sensitivity replay. Provider factors are hypotheses, not settlement records."""
from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

from aoae.etf_risk_overlay import build_overlay_schedule
from aoae.small_account import execution_cost, target_lots


@dataclass(frozen=True)
class Action:
    symbol: str
    date: pd.Timestamp
    ratio: float
    cash_per_old_share: float
    payment_date: pd.Timestamp | None = None
    rounding: str = 'floor'


def infer_actions(symbol, rows):
    """Explicit assumption: s is cumulative split factor, u cumulative cash/share.

    Simultaneous split/cash changes are rejected because units are ambiguous.
    """
    ordered = sorted(rows, key=lambda row: row['d'])
    if not ordered or ordered[0]['d'] != '1900-01-01':
        raise ValueError('factor baseline missing')
    if len({r['d'] for r in ordered}) != len(ordered):
        raise ValueError('duplicate factor dates')
    previous_s, previous_u = 1., 0.
    actions = []
    for row in ordered:
        s, u, f = float(row['s']), float(row['u']), float(row['f'])
        if not all(math.isfinite(v) for v in (s, u, f)) or s <= 0 or f != 1:
            raise ValueError('unsupported factor value')
        ratio, cash = s / previous_s, u - previous_u
        if cash < -1e-9 or (abs(ratio - 1) > 1e-9 and abs(cash) > 1e-9):
            raise ValueError('ambiguous cash and split units')
        if row['d'] != '1900-01-01' and (abs(ratio - 1) > 1e-9 or cash > 1e-9):
            actions.append(Action(symbol, pd.Timestamp(row['d']), ratio, max(0., cash)))
        previous_s, previous_u = s, u
    return actions


def total_return_signals(raw_close, actions):
    """Forward-only wealth index; future factor events do not revise past signals."""
    ratio = pd.DataFrame(1., index=raw_close.index, columns=raw_close.columns)
    cash = pd.DataFrame(0., index=raw_close.index, columns=raw_close.columns)
    for action in actions:
        if raw_close.index[0] < action.date <= raw_close.index[-1]:
            if action.date not in raw_close.index:
                raise ValueError('action date absent from common calendar')
            ratio.at[action.date, action.symbol] = action.ratio
            cash.at[action.date, action.symbol] = action.cash_per_old_share
    gross = (raw_close * ratio + cash) / raw_close.shift(1)
    gross.iloc[0] = 1.
    if not np.isfinite(gross.to_numpy()).all() or (gross <= 0).any().any():
        raise ValueError('invalid total-return index')
    return gross.cumprod()


def replay(opens, closes, schedule, actions, risk_assets, start, end,
           initial=300000., commission=.003, slippage_bps=30., pay_lag_sessions=5,
           pause_loss=100000., use_payment_dates=False, buy_fill_fraction=1.):
    """Prior-close sized drafts; next-open adverse fills, sell first, no leverage.

    Dividends accrue on assumed ex-date and become cash after the specified lag.
    Unknown exact split rounding is conservatively floored and loss disclosed.
    Paused accounts liquidate at the following observed open and never re-enter.
    """
    if pay_lag_sessions < 0 or int(pay_lag_sessions) != pay_lag_sessions:
        raise ValueError('invalid payment lag')
    if not math.isfinite(buy_fill_fraction) or not 0 <= buy_fill_fraction <= 1:
        raise ValueError('invalid buy fill fraction')
    assets = tuple(risk_assets)
    dates = closes.index[(closes.index >= start) & (closes.index <= end)]
    locations = {d: i for i, d in enumerate(closes.index)}
    events = {}
    for action in actions:
        events.setdefault(action.date, []).append(action)
    quantity = {s: 0 for s in assets}
    cash, receivables, equity, records = initial, [], [], []
    paused, total_cost, rounding_loss = False, 0., 0.
    for date in dates:
        i = locations[date]
        for action in events.get(date, []):
            if action.symbol not in quantity:
                continue
            old = quantity[action.symbol]
            entitlement = old * action.cash_per_old_share
            if entitlement:
                if use_payment_dates:
                    if action.payment_date is None or action.payment_date < date:
                        raise ValueError('valid payment date required')
                    due = int(closes.index.searchsorted(action.payment_date))
                else:
                    due = i + pay_lag_sessions
                receivables.append((due, entitlement))
            exact = old * action.ratio
            if action.rounding not in {'floor', 'ceil'}:
                raise ValueError('unknown share rounding rule')
            quantity[action.symbol] = math.ceil(exact - 1e-9) if action.rounding == 'ceil' else math.floor(exact + 1e-9)
            rounding_loss += max(0., exact - quantity[action.symbol]) * float(opens.at[date, action.symbol])
        cash += sum(amount for due, amount in receivables if due <= i)
        receivables = [(due, amount) for due, amount in receivables if due > i]
        targets = None
        if paused:
            targets = {s: 0 for s in assets}
        elif date in schedule:
            weights, _, signal_date, _ = schedule[date]
            previous = closes.iloc[i - 1].copy()
            if pd.Timestamp(signal_date) != closes.index[i - 1]:
                raise ValueError('signal is not previous common close')
            # Known actions adjust the reference price and holdings consistently.
            # Public pre-open announcement availability is not established here.
            for action in events.get(date, []):
                previous[action.symbol] = (previous[action.symbol] - action.cash_per_old_share) / action.ratio
            pre_value = cash + sum(a for _, a in receivables) + sum(quantity[s] * previous[s] for s in assets)
            targets = target_lots(pre_value, {s: weights.get(s, 0.) for s in assets}, previous, 100)
        if targets is not None:
            for side in ('SELL', 'BUY'):
                for s in assets:
                    delta = targets[s] - quantity[s]
                    if (side == 'SELL' and delta >= 0) or (side == 'BUY' and delta <= 0):
                        continue
                    count = abs(delta)
                    if side == 'BUY':
                        count = math.floor(count * buy_fill_fraction / 100) * 100
                    price = float(opens.at[date, s])
                    if side == 'BUY':
                        while count and count * price + execution_cost(count * price, commission, 5., slippage_bps) > cash:
                            count -= 100
                    if not count:
                        continue
                    fee = execution_cost(count * price, commission, 5., slippage_bps)
                    direction = 1 if side == 'BUY' else -1
                    cash -= direction * count * price + fee
                    quantity[s] += direction * count
                    total_cost += fee
                    records.append({'date': str(date.date()), 'symbol': s, 'side': side, 'quantity': int(count), 'price': price, 'cost': fee})
        if cash < -1e-6:
            raise ValueError('negative cash')
        value = cash + sum(a for _, a in receivables) + sum(quantity[s] * closes.at[date, s] for s in assets)
        equity.append(value)
        if value <= initial - pause_loss:
            paused = True
    return pd.Series(equity, index=dates), records, {
        'paused': paused, 'cost_cny': round(total_cost, 2),
        'split_fraction_writeoff_cny': round(rounding_loss, 4),
        'ending_cash_cny': round(cash, 2),
        'ending_receivables_cny': round(sum(a for _, a in receivables), 2),
        'ending_positions': quantity,
    }
