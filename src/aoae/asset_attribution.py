"""Ex-post asset cash-flow attribution; never a signal or a causal alpha estimate."""
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR


def attribute(dates, closes, orders, actions, initial, rate, slippage_bps):
    def dec(x):
        value = Decimal(str(x))
        if not value.is_finite():
            raise ValueError('nonfinite attribution input')
        return value
    if not dates or dates != sorted(set(dates)):
        raise ValueError('invalid dates')
    assets = list(closes[dates[0]])
    fields = ('buy_notional', 'sell_notional', 'dividend_entitlement', 'commission', 'execution_loss', 'split_rounding_mark')
    accounts = {s: {k: Decimal(0) for k in fields} for s in assets}
    quantities = {s: 0 for s in assets}
    by_day, events = {}, {}
    for o in orders:
        if o['date'] not in dates or o['symbol'] not in assets:
            raise ValueError('order outside attribution scope')
        by_day.setdefault(o['date'], []).append(o)
    for a in actions:
        events.setdefault(a['date'], []).append(a)
    daily = []
    for day in dates:
        if set(closes[day]) != set(assets) or any(dec(v) <= 0 for v in closes[day].values()):
            raise ValueError('invalid marks')
        for a in events.get(day, []):
            s = a['symbol']
            if s not in accounts:
                continue
            ratio, cash = dec(a['ratio']), dec(a['cash_per_old_share'])
            if ratio <= 0 or cash < 0:
                raise ValueError('invalid action')
            old = quantities[s]
            accounts[s]['dividend_entitlement'] += old * cash
            exact = old * ratio
            rounding = {'floor': ROUND_FLOOR, 'ceil': ROUND_CEILING}[a['rounding']]
            quantities[s] = int(exact.to_integral_value(rounding=rounding))
            accounts[s]['split_rounding_mark'] += (quantities[s] - exact) * dec(closes[day][s])
        for o in by_day.get(day, []):
            s, count = o['symbol'], o['quantity']
            if type(count) is not int or count <= 0 or dec(o['price']) <= 0:
                raise ValueError('invalid trade')
            notional = count * dec(o['price'])
            commission = max(Decimal(5), notional * dec(rate))
            loss = notional * dec(slippage_bps) / 10000
            if abs(commission + loss - dec(o['cost'])) > Decimal('.000001'):
                raise ValueError('fee mismatch')
            accounts[s]['commission'] += commission
            accounts[s]['execution_loss'] += loss
            if o['side'] == 'BUY':
                if count % 100:
                    raise ValueError('non-lot purchase')
                quantities[s] += count
                accounts[s]['buy_notional'] += notional
            elif o['side'] == 'SELL':
                if count > quantities[s]:
                    raise ValueError('uncovered sale')
                quantities[s] -= count
                accounts[s]['sell_notional'] += notional
            else:
                raise ValueError('invalid side')
        pnl = {}
        for s, a in accounts.items():
            gross = quantities[s] * dec(closes[day][s]) + a['sell_notional'] - a['buy_notional'] + a['dividend_entitlement']
            pnl[s] = gross - a['commission'] - a['execution_loss']
        daily.append({'date': day, 'asset_cumulative_net_pnl_cny': {s: float(v) for s, v in pnl.items()},
                      'reconstructed_equity_cny': float(dec(initial) + sum(pnl.values()))})
    output = {}
    for s, a in accounts.items():
        mark = quantities[s] * dec(closes[dates[-1]][s])
        exit_cost = max(Decimal(5), mark * dec(rate)) + mark * dec(slippage_bps) / 10000 if quantities[s] else Decimal(0)
        gross = mark + a['sell_notional'] - a['buy_notional'] + a['dividend_entitlement']
        net = gross - a['commission'] - a['execution_loss'] - exit_cost
        output[s] = {**{k + '_cny': float(v) for k, v in a.items()}, 'ending_quantity': quantities[s],
            'ending_market_value_cny': float(mark), 'gross_cashflow_pnl_cny': float(gross),
            'exit_haircut_cny': float(exit_cost), 'net_pnl_after_exit_haircut_cny': float(net)}
    return {'assets': output, 'daily': daily,
        'net_pnl_after_exit_haircut_cny': sum(a['net_pnl_after_exit_haircut_cny'] for a in output.values()),
        'scope': 'Ex-post cash-flow identity. Dividend paid vs receivable is not new PnL; split rounding diagnostic is already embedded, never added twice. Not factor alpha or a no-asset counterfactual.'}
