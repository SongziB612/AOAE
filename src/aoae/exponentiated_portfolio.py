"""Helmbold et al. (1998), equation 3.3; causal gross-gradient targets."""
import numpy as np
from scipy.special import logsumexp
from aoae.universal import relatives


def eg_weights(values, learning_rate):
    x = relatives(values)
    if not np.isfinite(learning_rate) or learning_rate < 0:
        raise ValueError('finite nonnegative learning rate required')
    logw = np.full(x.shape[1], -np.log(x.shape[1]))
    output = []
    for row in x:
        w = np.exp(logw)
        output.append(w.copy())
        scaled = row / row.max()
        gradient = scaled / (w @ scaled)
        update = learning_rate * gradient
        if not np.isfinite(update).all():
            raise ValueError('numerically unrepresentable update')
        logw = logw + update
        logw -= logsumexp(logw)
    return np.asarray(output)
