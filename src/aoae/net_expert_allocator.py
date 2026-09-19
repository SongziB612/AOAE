"""Causal net-wealth scoring, deliberately not labelled Cover's cost theorem."""
import numpy as np
from scipy.special import logsumexp

from aoae.universal import relatives, run_portfolio, simplex


def net_expert_weights(values, experts, costs):
    """Virtual CRP accounts pay costs independently; allocator fees are separate.

    Targets mix nominal CRP weights, not shares in funded expert accounts.
    Each virtual account has the same relative synthetic capacity assumption.
    Its fee is a scoring input only, never a second debit to allocator wealth.
    """
    x = relatives(values)
    grid = np.asarray(experts, dtype=float)
    if grid.ndim != 2 or len(grid) == 0:
        raise ValueError('empty expert set')
    for b in grid:
        simplex(b, x.shape[1])
    # Each run_portfolio recurrence is causal. Shift the completed virtual
    # wealth by one observation before constructing period-t allocations.
    logs = np.column_stack([np.log(run_portfolio(x, b, 1, costs)['wealth']) for b in grid])
    past = np.vstack([np.zeros(len(grid)), logs[:-1]])
    posterior = np.exp(past - logsumexp(past, axis=1)[:, None])
    return posterior @ grid, {
        'posterior': posterior,
        'expert_terminal_log_wealth': logs[-1],
        'expert_costs_debited_to_allocator': False,
        'interpretation': 'Causal nominal-weight mixture scored by virtual net CRP wealth; no costless mixture identity asserted.'
    }
