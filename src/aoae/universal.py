"""Long-only mathematical baselines; costed outputs remain synthetic research."""
from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp


def relatives(values):
    x = np.asarray(values, dtype=float)
    if x.ndim != 2 or min(x.shape) < 1 or not np.isfinite(x).all() or (x <= 0).any():
        raise ValueError('price relatives must be a nonempty positive finite matrix')
    return x


def simplex(values, size):
    b = np.asarray(values, dtype=float)
    if b.shape != (size,) or not np.isfinite(b).all() or (b < 0).any() or abs(b.sum() - 1) > 1e-10:
        raise ValueError('invalid simplex weights')
    return b


def bcrp(values):
    """EX POST gross log-optimal CRP, with a concave first-order gap bound."""
    x = relatives(values)
    m = x.shape[1]
    def objective(b):
        return -float(np.log(x @ b).sum())
    def jac(b):
        return -(x / (x @ b)[:, None]).sum(axis=0)
    fit = minimize(objective, np.full(m, 1 / m), jac=jac, method='SLSQP',
                   bounds=[(0., 1.)] * m,
                   constraints={'type': 'eq', 'fun': lambda b: b.sum() - 1,
                                'jac': lambda b: np.ones(m)},
                   options={'ftol': 1e-12, 'maxiter': 1000})
    if not fit.success:
        raise ValueError('BCRP optimization failed: ' + fit.message)
    b = np.maximum(fit.x, 0.)
    b /= b.sum()
    g = -jac(b)
    gap = max(0., float(g.max() - b @ g))
    if gap > 1e-5:
        raise ValueError('BCRP numerical certificate too loose')
    return {'weights': b, 'log_wealth': -objective(b), 'log_optimality_gap_bound': gap,
            'information_class': 'EX_POST_OPTIMUM', 'net_cost_optimal': False}


def two_asset_grid(points):
    if type(points) is not int or points < 2:
        raise ValueError('at least two grid points required')
    a = np.linspace(0, 1, points)
    return np.column_stack([a, 1 - a])


def universal_weights(values, experts):
    """Finite-mixture Cover approximation, updated strictly AFTER each return."""
    x = relatives(values)
    grid = np.asarray(experts, dtype=float)
    if grid.ndim != 2 or len(grid) == 0:
        raise ValueError('empty expert set')
    for b in grid:
        simplex(b, x.shape[1])
    log_wealth = np.zeros(len(grid))
    allocations = []
    for row in x:
        posterior = np.exp(log_wealth - logsumexp(log_wealth))
        allocations.append(posterior @ grid)
        log_wealth += np.log(grid @ row)
    return np.asarray(allocations), float(logsumexp(log_wealth) - np.log(len(grid)))


@dataclass(frozen=True)
class SyntheticCosts:
    commission_bps: float
    half_spread_bps: float
    slippage_bps: float
    impact_bps_at_full_volume: float
    volume_to_account_equity: float
    maximum_participation: float

    def validate(self):
        vals = list(vars(self).values())
        if not all(np.isfinite(v) and v > 0 for v in vals):
            raise ValueError('all synthetic cost/capacity inputs must be positive')
        if self.maximum_participation > 1 or self.rate >= .1:
            raise ValueError('invalid participation or cost rate')

    @property
    def rate(self):
        # Conservative impact charge at the maximum allowed participation.
        return (self.commission_bps + self.half_spread_bps + self.slippage_bps +
                self.impact_bps_at_full_volume * self.maximum_participation) / 10000


def _funded_target(old, target, rate):
    mu = 1.
    for _ in range(100):
        next_mu = 1 - rate * np.abs(mu * target[:-1] - old[:-1]).sum()
        if abs(mu - next_mu) < 1e-14:
            mu = next_mu
            break
        mu = next_mu
    turnover = float(np.abs(mu * target[:-1] - old[:-1]).sum())
    if mu <= 0 or abs(1 - mu - rate * turnover) > 1e-10:
        raise ValueError('self-financing cost equation failed')
    return mu, turnover


def run_portfolio(values, weights, rebalance_every=1, costs=None):
    """Weights are pre-return targets. Cash is explicit; cap-induced misses cancel.

    rebalance_every=None means one initial allocation then buy-and-hold.
    costs=None is a FRICTIONLESS_MATHEMATICAL_DIAGNOSTIC, never execution evidence.
    """
    x = relatives(values)
    n, m = x.shape
    w = np.asarray(weights, dtype=float)
    if w.ndim == 1:
        w = np.repeat(simplex(w, m)[None, :], n, axis=0)
    if w.shape != x.shape:
        raise ValueError('allocation shape differs from relatives')
    for row in w:
        simplex(row, m)
    if rebalance_every is not None and (type(rebalance_every) is not int or rebalance_every < 1):
        raise ValueError('invalid rebalancing interval')
    if costs:
        costs.validate()
    wealth, old = 1., np.r_[np.zeros(m), 1.]
    equity, turns, fees, logfees, executed, capped = [], [], [], [], [], []
    trade_legs = 0
    for t in range(n):
        do_trade = t == 0 or (rebalance_every is not None and t % rebalance_every == 0)
        target = np.r_[w[t], 0.] if do_trade else old.copy()
        rate = costs.rate if costs else 0.
        mu, turn = _funded_target(old, target, rate)
        was_capped = False
        if costs and turn > costs.maximum_participation * costs.volume_to_account_equity:
            cap = costs.maximum_participation * costs.volume_to_account_equity
            desired, lo, hi = target.copy(), 0., 1.
            for _ in range(45):
                mid = (lo + hi) / 2
                candidate = old + mid * (desired - old)
                _, candidate_turn = _funded_target(old, candidate, rate)
                if candidate_turn <= cap:
                    lo = mid
                else:
                    hi = mid
            target = old + lo * (desired - old)
            mu, turn = _funded_target(old, target, rate)
            was_capped = True
        trade_legs += int((np.abs(mu * target[:-1] - old[:-1]) > 1e-10).sum())
        fee = wealth * (1 - mu)
        growth = float(target[:-1] @ x[t] + target[-1])
        wealth *= mu * growth
        old = target * np.r_[x[t], 1.] / growth
        equity.append(wealth)
        turns.append(turn)
        fees.append(fee)
        logfees.append(-np.log(mu))
        executed.append(target.copy())
        capped.append(was_capped)
    return {'wealth': np.asarray(equity), 'turnover': np.asarray(turns),
            'fees': np.asarray(fees), 'log_fee_drag': float(sum(logfees)),
            'executed_weights_including_cash': np.asarray(executed),
            'trade_legs': trade_legs, 'capacity_capped_periods': sum(capped),
            'information_class': 'SYNTHETIC_COSTED_PROXY' if costs else 'FRICTIONLESS_MATHEMATICAL_DIAGNOSTIC'}
