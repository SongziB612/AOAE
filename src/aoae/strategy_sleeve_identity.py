"""Accounting identity for fixed, scalable expert-return streams, not fills."""
import numpy as np


def inspect_sleeve_mixture(net_returns):
    r = np.asarray(net_returns, dtype=float)
    if r.ndim != 2 or not all(r.shape) or not np.isfinite(r).all() or (r <= -1).any():
        raise ValueError('complete finite returns greater than -1 required')
    n, k = r.shape
    wealth = np.ones(k)
    account = 1.
    previous_post_return = np.full(k, 1/k)
    rows = []
    for t in range(n):
        weights = wealth / wealth.sum()
        transfer = float(np.abs(weights-previous_post_return).sum())
        growth = float(weights @ (1+r[t]))
        account *= growth
        previous_post_return = weights*(1+r[t])/growth
        wealth *= 1+r[t]
        if not np.isfinite(wealth).all() or not np.isfinite(account):
            raise ValueError('nonfinite compounded wealth')
        rows.append({'wealth':account, 'buy_hold_sleeves_wealth':float(wealth.mean()),
                     'pre_return_weights':weights.tolist(), 'inter_sleeve_transfer':transfer})
    return {'rows':rows, 'terminal_wealth':account,
            'maximum_identity_error':max(abs(x['wealth']-x['buy_hold_sleeves_wealth']) for x in rows),
            'maximum_inter_sleeve_transfer':max(x['inter_sleeve_transfer'] for x in rows),
            'limits':'Fixed scalable returns assumption only. Underlying strategies still trade and pay costs; minimum fees, lots and capacity break scalable-sleeve interpretation.',
            'capital_authorized':False}
