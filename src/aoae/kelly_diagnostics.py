"""Known-distribution binary toy model; NOT a live sizing estimator."""
import math


def binary_diagnostic(p, b, fraction, n=100, barrier=0.2):
    """Barrier is <= initial wealth * barrier, not peak-relative drawdown.

    Independent fixed-odds bets, no costs/gaps/rounding or forced liquidation.
    Terminal distribution continues even after barrier breach. Exact finite-state
    probabilities (up to floating point), not Monte Carlo or market forecasts.
    """
    if (not all(math.isfinite(x) for x in (p, b, fraction, barrier))
            or not 0 <= p <= 1 or b <= 0 or not 0 <= fraction < 1
            or not 0 < barrier < 1 or type(n) is not int or not 0 <= n <= 1000):
        raise ValueError("invalid binary model parameters")
    win, loss = math.log1p(fraction * b), math.log1p(-fraction)
    log_barrier = math.log(barrier)
    terminal_loss = terminal_barrier = 0.0
    for w in range(n + 1):
        prob = math.comb(n, w) * p ** w * (1 - p) ** (n - w)
        wealth_log = w * win + (n - w) * loss
        terminal_loss += prob * (wealth_log < -1e-14)
        terminal_barrier += prob * (wealth_log <= log_barrier + 1e-14)
    alive = {0: 1.0}
    hit = 0.0
    for t in range(1, n + 1):
        next_alive = {}
        for w, prob in alive.items():
            for wins, branch_prob in ((w, prob * (1 - p)), (w + 1, prob * p)):
                if wins * win + (t - wins) * loss <= log_barrier + 1e-14:
                    hit += branch_prob
                else:
                    next_alive[wins] = next_alive.get(wins, 0.0) + branch_prob
        alive = next_alive
    return {
        "p": p, "b": b, "fraction": fraction, "bets": n, "barrier": barrier,
        "long_only_kelly_fraction": max(0.0, (p * b - (1 - p)) / b),
        "expected_log_growth_per_bet": p * win + (1 - p) * loss,
        "simple_return_variance": fraction ** 2 * p * (1 - p) * (b + 1) ** 2,
        "terminal_loss_probability": terminal_loss,
        "terminal_barrier_probability": terminal_barrier,
        "ever_barrier_probability": hit,
        "finite_exact_zero_probability": 0.0,
        "probability_mass_error": abs(hit + math.fsum(alive.values()) - 1),
    }
