"""Selection diagnostics, not capital gates. All Sharpe inputs are per-period.

DSR follows Bailey/Lopez de Prado (2014), eq. 2, under IID moments.
CSCV follows Bailey et al. PBO; folds are diagnostic, not chronological holdouts.
"""
from itertools import combinations
from math import e, sqrt
from statistics import NormalDist
import numpy as np


def deflated_sharpe(returns, independent_trials, trial_sharpe_variance):
    r = np.asarray(returns, dtype=float)
    if r.ndim != 1 or len(r) < 4 or not np.isfinite(r).all():
        raise ValueError('finite one-dimensional returns required')
    if type(independent_trials) is not int or independent_trials < 1:
        raise ValueError('positive integer trial assumption required')
    if not np.isfinite(trial_sharpe_variance) or trial_sharpe_variance < 0:
        raise ValueError('invalid across-trial per-period Sharpe variance')
    sd = r.std(ddof=1)
    if sd <= 0:
        raise ValueError('zero return variance')
    sr = float(r.mean() / sd)
    centered = r - r.mean()
    m2 = np.mean(centered ** 2)
    skew = float(np.mean(centered ** 3) / m2 ** 1.5)
    kurtosis = float(np.mean(centered ** 4) / m2 ** 2)  # Pearson, not excess
    normal, gamma = NormalDist(), 0.5772156649015329
    n = independent_trials
    benchmark = 0.0 if n == 1 else sqrt(trial_sharpe_variance) * (
        (1 - gamma) * normal.inv_cdf(1 - 1 / n) + gamma * normal.inv_cdf(1 - 1 / (n * e)))
    denominator = 1 - skew * sr + (kurtosis - 1) * sr * sr / 4
    if denominator <= 0:
        raise ValueError('invalid Sharpe uncertainty')
    return {'dsr_iid_sensitivity': normal.cdf((sr - benchmark) * sqrt(len(r) - 1) / sqrt(denominator)),
            'sharpe_per_period': sr, 'benchmark_per_period': benchmark,
            'assumed_independent_trials': n, 'trial_sharpe_variance': float(trial_sharpe_variance),
            'observations': len(r), 'skewness': skew, 'pearson_kurtosis': kurtosis,
            'serial_dependence_adjusted': False}


def cscv_pbo(returns, blocks=8, balanced=False):
    x = np.asarray(returns, dtype=float)
    if x.ndim != 2 or x.shape[1] < 2 or not np.isfinite(x).all():
        raise ValueError('complete finite date-by-candidate matrix required')
    if type(blocks) is not int or blocks < 4 or blocks > 12 or blocks % 2 or len(x) < blocks * 2:
        raise ValueError('even 4..12 blocks and at least two observations each required')
    # Require equal-size contiguous blocks; never silently trim data.
    if len(x) % blocks and not balanced:
        raise ValueError('observations must divide evenly into blocks')
    chunks = np.array_split(np.arange(len(x)), blocks)
    failures, total, tied_selections = 0.0, 0, 0
    def scores(rows):
        part = x[rows]
        sd = part.std(axis=0, ddof=1)
        if np.any(sd <= 0):
            raise ValueError('degenerate candidate in a fold')
        return part.mean(axis=0) / sd
    for selected in combinations(range(blocks), blocks // 2):
        train = scores(np.concatenate([chunks[i] for i in selected]))
        test = scores(np.concatenate([chunks[i] for i in range(blocks) if i not in selected]))
        winners = np.flatnonzero(train == train.max())
        tied_selections += int(len(winners) > 1)
        losses = []
        for winner in winners:
            # Average tied ranks, ascending; divide by N+1 as in CSCV.
            rank = np.sum(test < test[winner]) + (np.sum(test == test[winner]) + 1) / 2
            percentile = rank / (x.shape[1] + 1)
            losses.append(float(percentile < .5) + .5 * float(percentile == .5))
        failures += float(np.mean(losses))
        total += 1
    return {'subset_pbo': failures / total, 'splits': total, 'blocks': blocks,
            'block_sizes': [len(c) for c in chunks],
            'method': 'BALANCED_BLOCK_CSCV_EXTENSION' if len(x) % blocks else 'EQUAL_BLOCK_CSCV',
            'is_tied_selection_splits': tied_selections,
            'tie_policy': 'Average IS winners; half failure at OOS median (explicit neutral-tie extension).',
            'chronological_holdout': False, 'purged_or_embargoed': False}


def comparable_matrix(runs, arms, initial):
    if len(runs) != len(arms) or len(set(arms)) != len(arms):
        raise ValueError('missing or duplicate candidates')
    by_arm = {r['arm']: r for r in runs}
    if set(by_arm) != set(arms):
        raise ValueError('wrong candidates')
    dates = by_arm[arms[0]]['dates']
    if not dates or dates != sorted(set(dates)):
        raise ValueError('invalid dates')
    columns = []
    for arm in arms:
        run = by_arm[arm]
        if run['dates'] != dates:
            raise ValueError('calendar mismatch: no intersection/dropna allowed')
        nav = np.array(run['equity_cny'], dtype=float)
        if len(nav) != len(dates) or not np.isfinite(nav).all() or np.any(nav <= 0) or initial <= 0:
            raise ValueError('invalid NAV')
        # Include the separately reported terminal liquidation haircut; do not
        # mistake marked NAV for after-exit wealth. Source PnL is cent-rounded.
        nav[-1] = initial + run['net_pnl_after_exit_haircut_cny']
        if nav[-1] <= 0:
            raise ValueError('nonpositive terminal wealth')
        columns.append(nav / np.r_[initial, nav[:-1]] - 1)
    return dates, np.column_stack(columns)
