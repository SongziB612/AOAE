"""Independent equal-asset risk control; does not inherit momentum exposure."""
import numpy as np


def equal_vol_weights(close, position, assets, lookback=63, target=.12):
    if type(lookback) is not int or lookback < 2 or position < lookback or position >= len(close):
        raise ValueError('insufficient or invalid lookback')
    if not assets or len(set(assets)) != len(assets) or not np.isfinite(target) or target <= 0:
        raise ValueError('invalid assets or target')
    prices = close.loc[:, list(assets)].iloc[position - lookback:position + 1]
    if not np.isfinite(prices.to_numpy()).all() or (prices <= 0).any().any():
        raise ValueError('invalid historical window')
    returns = prices.pct_change().dropna()
    vector = np.full(len(assets), 1 / len(assets))
    variance = float(vector @ (returns.cov().to_numpy() * 252) @ vector)
    if not np.isfinite(variance) or variance <= 0:
        raise ValueError('nonpositive trailing basket variance')
    exposure = min(1., target / np.sqrt(variance))
    return {s: exposure / len(assets) for s in assets}
