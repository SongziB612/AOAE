"""Explicit log-growth, tail, dependence and decomposition diagnostics."""
import numpy as np


def metrics(result, periods_per_year=252, distress_threshold=.2):
    wealth = result['wealth']
    returns = wealth / np.r_[1., wealth[:-1]] - 1
    logs = np.log1p(returns)
    n = len(returns)
    vol = float(returns.std(ddof=1)) if n > 1 else 0.
    downside = float(np.sqrt(np.mean(np.minimum(returns, 0) ** 2)))
    peaks = np.maximum.accumulate(np.r_[1., wealth])[1:]
    drawdown = wealth / peaks - 1
    duration, maximum_duration = 0, 0
    for value in drawdown:
        duration = duration + 1 if value < -1e-12 else 0
        maximum_duration = max(maximum_duration, duration)
    annual_log = float(logs.mean() * periods_per_year)
    cagr = float(np.expm1(annual_log))
    ac_sum = 0.
    if n > 3 and vol > 1e-12:
        centered = returns - returns.mean()
        denominator = float(centered @ centered)
        for lag in range(1, min(20, n // 4) + 1):
            rho = float(centered[:-lag] @ centered[lag:] / denominator)
            if rho <= 0:
                break
            ac_sum += rho
    ess = float(n / (1 + 2 * ac_sum))
    return {'raw_observations': n, 'raw_trade_legs': result['trade_legs'],
            'serial_ess_heuristic': ess, 'ess_limit': 'Positive-ACF truncation only; not independent markets, trades or regime samples.',
            'terminal_wealth': float(wealth[-1]), 'cagr': cagr,
            'geometric_growth_per_period': float(np.expm1(logs.mean())),
            'log_wealth_growth': float(logs.sum()), 'annualized_log_growth': annual_log,
            'sharpe_zero_cash_rate': float(returns.mean() / vol * np.sqrt(periods_per_year)) if vol > 1e-12 else None,
            'sortino_zero_target': float(returns.mean() / downside * np.sqrt(periods_per_year)) if downside > 1e-12 else None,
            'max_drawdown': float(drawdown.min()), 'drawdown_duration_periods': maximum_duration,
            'calmar': cagr / abs(float(drawdown.min())) if drawdown.min() < -1e-12 else None,
            'annualized_volatility': vol * np.sqrt(periods_per_year),
            'turnover_sum_absolute_traded_fraction': float(result['turnover'].sum()),
            'transaction_cost_initial_wealth_units': float(result['fees'].sum()),
            'log_fee_drag': result['log_fee_drag'],
            'expected_shortfall_loss_95': float(-np.sort(returns)[:max(1, int(np.ceil(n * .05)))].mean()),
            'worst_period_return': float(returns.min()),
            'observed_distress_breach': bool((wealth <= distress_threshold).any()),
            'distress_threshold_fraction_initial': distress_threshold,
            'risk_of_ruin_probability': None, 'ruin_reason': 'Not identifiable from this synthetic path; breach frequency is not a real-market probability.',
            'capacity_capped_periods': result['capacity_capped_periods']}


def decomposition(x, b):
    logs = np.log(x)
    asset_growth = logs.sum(axis=0)
    weighted = float(b @ asset_growth)
    crp_log = float(np.log(x @ b).sum())
    bh_log = float(np.log(b @ np.exp(asset_growth)))
    covariance = np.cov(x - 1, rowvar=False, ddof=1)
    diag = float(.5 * np.sum(b * (1 - b) * np.diag(covariance)))
    cross = float(-.5 * (b @ covariance @ b - np.sum(b * b * np.diag(covariance))))
    exact_mean = (crp_log - weighted) / len(x)
    corr = np.corrcoef(x.T) if np.all(np.std(x, axis=0) > 1e-12) else None
    return {'asset_log_growth': asset_growth.tolist(), 'weighted_asset_log_growth': weighted,
            'crp_log_growth': crp_log, 'buy_hold_log_growth': bh_log,
            'exact_diversification_log_growth': crp_log - weighted,
            'rebalancing_log_premium_vs_same_weight_buy_hold': crp_log - bh_log,
            'variance_contribution_small_return_approx_per_period': diag,
            'cross_covariance_contribution_small_return_approx_per_period': cross,
            'second_order_approximation_error_per_period': exact_mean - diag - cross,
            'sample_asset_correlation': corr.tolist() if corr is not None else None,
            'factor_alpha': None, 'factor_note': 'Synthetic generators, no admitted empirical risk factors or neutralization.'}
