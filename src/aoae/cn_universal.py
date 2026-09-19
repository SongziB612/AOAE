"""Finite-lattice monthly UP targets for the existing CN raw-price replay."""
import numpy as np
import pandas as pd
from scipy.special import logsumexp


def simplex_lattice(assets, units):
    if type(assets) is not int or type(units) is not int or assets < 2 or units < 1:
        raise ValueError('invalid simplex lattice size')
    def compositions(left, count):
        if count == 1:
            yield (left,)
        else:
            for x in range(left + 1):
                for rest in compositions(left - x, count - 1):
                    yield (x,) + rest
    return np.asarray(list(compositions(units, assets)), dtype=float) / units


def monthly_schedules(index, assets, start, end, units):
    """Reset expert prior per evaluation year; no cross-year winner selection.

    Uses monthly forward total-return closes through the session BEFORE order.
    Expert scores are frictionless nominal CRPs; actual account pays all costs.
    This is not exact continuous Cover or an identity for next-open executions.
    """
    if not index.index.is_unique or not index.index.is_monotonic_increasing:
        raise ValueError('invalid dates')
    data = index.loc[:, list(assets)]
    if not np.isfinite(data.to_numpy()).all() or (data <= 0).any().any():
        raise ValueError('invalid forward index')
    dates = data.index[(data.index >= start) & (data.index <= end)]
    if not len(dates) or data.index.get_loc(dates[0]) == 0:
        raise ValueError('prior session required')
    grid = simplex_lattice(len(assets), units)
    logs, previous, month = np.zeros(len(grid)), None, None
    schedules = {name: {} for name in ('up_monthly', 'equal_monthly', 'equal_buy_hold')}
    equal = {s: 1 / len(assets) for s in assets}
    for day in dates:
        key = (day.year, day.month)
        if key == month:
            continue
        month = key
        prior = data.index[data.index.get_loc(day) - 1]
        observed = data.loc[prior].to_numpy(dtype=float)
        if previous is not None:
            logs += np.log(grid @ (observed / previous))
        weights = np.exp(logs - logsumexp(logs)) @ grid
        schedules['up_monthly'][day] = (dict(zip(assets, weights, strict=True)), {}, str(prior.date()), {})
        schedules['equal_monthly'][day] = (equal.copy(), {}, str(prior.date()), {})
        if previous is None:
            schedules['equal_buy_hold'][day] = (equal.copy(), {}, str(prior.date()), {})
        previous = observed
    return schedules
