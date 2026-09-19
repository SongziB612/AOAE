"""Causal frozen three-arm weights. Data review is an explicit upstream gate."""
import numpy as np
import pandas as pd

from aoae.corporate_action_replay import total_return_signals
from aoae.etf_risk_overlay import overlay_weights


ARMS = ('causal_total_return_momentum_overlay', 'monthly_same_universe_equal_weight',
        'monthly_same_universe_exposure_matched_equal_weight')


def frozen_weights(closes, actions, spec, signal_date):
    """Crop before calculating, including actions: future observations cannot leak.

    This reproduces the raw-price comparison: unused defensive weight is CASH,
    not a purchase of the defensive ETF. Callers must not treat a draft as a trade.
    """
    date = pd.Timestamp(signal_date)
    if closes.index.has_duplicates or not closes.index.is_monotonic_increasing:
        raise ValueError('invalid price calendar')
    if set(closes.columns) != set(spec.symbols) or date not in closes.index:
        raise ValueError('incomplete universe or absent signal day')
    panel = closes.loc[:date]
    if not np.isfinite(panel.to_numpy()).all() or (panel <= 0).any().any():
        raise ValueError('invalid prices')
    known_actions = [a for a in actions if a.date <= date]
    returns = total_return_signals(panel, known_actions)
    weights, scores, diagnostics = overlay_weights(returns, len(returns) - 1, spec, 63, .12)
    model = {s: weights[s] for s in spec.risk_assets}
    exposure = sum(model.values())
    return {'weights': {ARMS[0]: model,
                        ARMS[1]: {s: 1 / len(model) for s in model},
                        ARMS[2]: {s: exposure / len(model) for s in model}},
            'cash_weights': {ARMS[0]: 1 - exposure, ARMS[1]: 0., ARMS[2]: 1 - exposure},
            'scores': scores, 'diagnostics': diagnostics,
            'status': 'DRAFT_REQUIRES_CALENDAR_ACTION_AND_INPUT_REVIEW',
            'capital_authorized': False, 'orders_authorized': False}
