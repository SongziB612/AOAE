"""Causal drift-only no-trade filter, not an optimal-control theorem replica."""
from aoae.shadow_accounting import dec


def filter_target(account, target, previous_target, prior_close, band):
    threshold = dec(band)
    if not 0 <= threshold <= 1:
        raise ValueError('invalid band')
    if target is None:
        return None, 'NO_REBALANCE'
    weights = {s: dec(w) for s, w in target.items()}
    if set(weights) != set(prior_close) or any(w < 0 for w in weights.values()) or sum(weights.values()) > dec('1.000000000001'):
        raise ValueError('invalid target universe/weights')
    equity = dec(account['equity'])
    if equity <= 0 or any(dec(p) <= 0 for p in prior_close.values()):
        raise ValueError('invalid prior valuation')
    if account['paused'] or threshold == 0 or previous_target is None:
        return target, 'BYPASS_INITIAL_PAUSE_OR_CONTROL'
    held = {s for s, q in account['positions'].items() if q}
    desired = {s for s, w in weights.items() if w > 0}
    if held != desired:
        return target, 'ASSET_CHANGE'
    if set(previous_target) != set(weights):
        raise ValueError('previous target universe changed')
    if sum(weights.values()) < sum(dec(w) for w in previous_target.values()) - dec('0.000000000001'):
        return target, 'RISK_REDUCTION'
    distance = max(abs(weights[s] - dec(account['positions'].get(s, 0)) * dec(prior_close[s]) / equity) for s in weights)
    if distance <= threshold:
        return None, 'SKIP_SMALL_DRIFT'
    return target, 'OUTSIDE_BAND'
