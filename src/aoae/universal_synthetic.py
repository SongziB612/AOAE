"""Seven fixed falsification worlds, deliberately not disguised as market data."""
import numpy as np


def generate(name, periods, seed):
    rng = np.random.default_rng(seed)
    z = rng.standard_normal((periods, 2))
    if name in {'high_vol_low_corr', 'high_vol_high_corr', 'low_vol_low_corr'}:
        rho = .95 if name == 'high_vol_high_corr' else 0.
        sigma = .003 if name == 'low_vol_low_corr' else .04
        shocks = np.column_stack([z[:, 0], rho * z[:, 0] + np.sqrt(1 - rho * rho) * z[:, 1]])
        return np.exp(sigma * shocks)  # zero expected log asset growth, not guaranteed realized growth
    if name == 'one_way_trend':
        return np.tile([1.008, .998], (periods, 1))
    if name == 'relative_mean_reversion':
        relative = np.zeros(periods + 1)
        for t in range(periods):
            relative[t + 1] = .5 * relative[t] + .08 * z[t, 0]
        changes = np.diff(relative)
        return np.exp(np.column_stack([changes, -changes]))
    if name == 'crash_correlation_spike':
        logs = .0002 + .012 * z
        start, stop = periods // 2, periods // 2 + max(5, periods // 20)
        shared = -.09 + .005 * z[start:stop, 0]
        logs[start:stop] = shared[:, None]
        return np.exp(logs)
    if name == 'permanent_loser':
        return np.tile([1.001, .96], (periods, 1))
    raise ValueError('unknown synthetic world')
