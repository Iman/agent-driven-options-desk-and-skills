"""Performance statistics, and honest tests of whether they mean anything.

Copyright (C) 2026 Iman Samizadeh. Licensed under AGPL-3.0-only.

A backtest produces a mean return. The interesting question is never the
mean, it is whether a mean that size could easily have arisen by chance
from a rule with no edge at all. These functions answer that with a
permutation test and a bootstrap interval rather than with a Sharpe ratio
quoted to two decimal places and no interval at all.

None of this addresses the deeper problem, which is that a strategy chosen
after looking at the data has already used the data. A p-value from a
single test on a single rule that was picked because it looked good is not
a p-value. That caveat is returned alongside the number.
"""

import math
import random

TRADING_DAYS = 252


def _mean(values):
    return sum(values) / len(values) if values else 0.0


def _stdev(values):
    if len(values) < 2:
        return 0.0
    mean = _mean(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1))


def performance_stats(returns, holding_days=None):
    """Summary statistics for a series of per-trade returns.

    returns are per-trade fractional profits on the capital each trade put
    at risk. Annualisation is deliberately optional and only applied when
    the holding period is known, because annualising a handful of trades of
    unknown length produces an impressive number that means nothing.
    """
    if not returns:
        return None
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r < 0]
    mean = _mean(returns)
    stdev = _stdev(returns)

    # Each trade risks one unit of capital, so the curve is the cumulative
    # SUM of returns on risk, not their compounded product. Compounding
    # would assume the entire account is risked on every trade and rolled
    # into the next, which drives the curve to zero the first time a
    # defined-risk structure loses its full risk, and reports a total
    # return of minus one hundred percent for a rule that lost fourteen
    # percent of one unit per trade.
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    curve = []
    for value in returns:
        equity += value
        curve.append(equity)
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)

    stats = {
        "trades": len(returns),
        "win_rate": len(wins) / len(returns),
        "mean_return": mean,
        "median_return": sorted(returns)[len(returns) // 2],
        "stdev": stdev,
        "best": max(returns),
        "worst": min(returns),
        "mean_win": _mean(wins) if wins else 0.0,
        "mean_loss": _mean(losses) if losses else 0.0,
        "profit_factor": (sum(wins) / abs(sum(losses))
                          if losses and sum(losses) != 0 else None),
        "total_return_on_risk": equity,
        "max_drawdown_in_risk_units": max_drawdown,
        "equity_curve": curve,
        "accounting": ("one unit of capital at risk per trade, returns "
                       "summed rather than compounded, so the curve and the "
                       "drawdown are in units of per-trade risk"),
        "sharpe_per_trade": (mean / stdev) if stdev > 0 else None,
    }
    if holding_days and holding_days > 0 and stdev > 0:
        trades_per_year = TRADING_DAYS / holding_days
        stats["sharpe_annualised"] = (mean / stdev) * math.sqrt(
            trades_per_year)
        stats["trades_per_year"] = trades_per_year
    return stats


def permutation_p_value(returns, trials=2000, seed=17):
    """How often a no-edge rule beats this mean by chance.

    The null is that the sign of each trade's return is arbitrary, which is
    what a rule with no directional or structural edge would produce. Signs
    are flipped at random and the mean recomputed; the p-value is the share
    of shuffles whose mean is at least as extreme as the observed one.

    Two-sided, because a rule that reliably loses is also a finding.
    """
    if len(returns) < 5:
        return None
    observed = abs(_mean(returns))
    rng = random.Random(seed)
    at_least_as_extreme = 0
    for _ in range(trials):
        shuffled = [value if rng.random() < 0.5 else -value
                    for value in returns]
        if abs(_mean(shuffled)) >= observed:
            at_least_as_extreme += 1
    return {
        "p_value": (at_least_as_extreme + 1) / float(trials + 1),
        "trials": trials,
        "observed_mean": _mean(returns),
        "null": ("the sign of each trade's return is arbitrary, which is "
                 "what a rule with no edge produces"),
        "caveat": ("A p-value is only a p-value for a hypothesis chosen "
                   "before seeing the data. A rule selected because its "
                   "backtest looked good has already spent its degrees of "
                   "freedom, and this number then understates how easily "
                   "the result could be chance."),
    }


def bootstrap_mean_interval(returns, trials=2000, level=0.90, seed=19):
    """Confidence interval for the mean return, by resampling trades."""
    if len(returns) < 5:
        return None
    rng = random.Random(seed)
    n = len(returns)
    means = []
    for _ in range(trials):
        sample = [returns[rng.randrange(n)] for _ in range(n)]
        means.append(_mean(sample))
    means.sort()
    lower_index = int((1.0 - level) / 2.0 * (trials - 1))
    upper_index = int((1.0 + level) / 2.0 * (trials - 1))
    return {
        "mean": _mean(returns),
        "lower": means[lower_index],
        "upper": means[upper_index],
        "level": level,
        "trials": trials,
        "excludes_zero": means[lower_index] > 0 or means[upper_index] < 0,
    }
