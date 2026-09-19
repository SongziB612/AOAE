"""Causal volatility-side-information EG; no hidden-state or alpha claim."""
import numpy as np
from scipy.special import logsumexp
from aoae.universal import relatives


def lagged_volatility_states(values, window, threshold):
    x = relatives(values)
    if type(window) is not int or window < 2 or not np.isfinite(threshold) or threshold <= 0:
        raise ValueError('window >=2 and positive finite threshold required')
    market_log = np.log(x).mean(axis=1)
    states = np.zeros(len(x), dtype=int)
    for t in range(window, len(x)):
        states[t] = int(market_log[t-window:t].std(ddof=1) >= threshold)
    return states


def conditional_weights(values, states, learning_rate):
    x = relatives(values)
    z = np.asarray(states)
    if z.shape != (len(x),) or not np.isin(z, [0, 1]).all():
        raise ValueError('one binary state per return required')
    if not np.isfinite(learning_rate) or learning_rate < 0:
        raise ValueError('finite nonnegative learning rate required')
    banks = np.full((2, x.shape[1]), -np.log(x.shape[1]))
    output = []
    for row, state in zip(x, z):
        state = int(state)
        weights = np.exp(banks[state])
        output.append(weights.copy())
        scaled = row / row.max()
        banks[state] += learning_rate * scaled / (weights @ scaled)
        if not np.isfinite(banks[state]).all():
            raise ValueError('nonfinite update')
        banks[state] -= logsumexp(banks[state])
    return np.asarray(output)
