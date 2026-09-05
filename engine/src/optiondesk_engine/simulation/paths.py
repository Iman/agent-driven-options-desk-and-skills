"""Forward paths from a fitted posterior, and what they imply for risk.

Copyright (C) 2026 Iman Samizadeh. Licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate written agreement.

One parameter draw per path, so parameter uncertainty is carried into the
fan rather than being collapsed to a point estimate first. That is the whole
reason for sampling a posterior instead of maximising a likelihood: a fan
built from one fitted parameter set is narrower than the data supports, and
a value at risk computed from it is comfortable in a way that is not earned.

THERE ARE NO ANTITHETIC PAIRS, AND THERE HAVE NOT BEEN FOR SOME TIME. This
module used to say that every drawn shock had its opposite run beside it,
and every artifact it wrote carried "antithetic": true. An audit measured
it: of ten thousand pairs, zero shared a shock sequence, and the
correlation between pair members was -0.016 where a working mirror gives
-1. The reason is visible once looked for. The sign loop drew its shocks
inside itself, so each side pulled fresh numbers from the stream, and
negating an independently drawn symmetric Student-t simply yields another
independent draw. The construction did nothing at all.

The test that guarded it asserted that the artifact's antithetic flag was
true, and the writer set that flag as an unconditional literal, so the test
asserted the claim rather than the property.

Removing it rather than repairing it, deliberately. The two halves of a
pair would have to share a parameter draw to mirror, and each path drawing
its own parameters is the more valuable of the two properties: the
docstring's own measurements, kept below, show mirroring helping the centre
and hurting the tail, and the tail is what a risk number is for.

    mean of terminal   0.035   mirroring far better
    median             0.25    better
    25th percentile    0.81    marginally better
    5th percentile     1.20    WORSE
    1st percentile     2.16    much worse
    value at risk 99   2.03    much worse

Those figures described a construction that was not running, and they are
retained here only to record why the repair was not the right answer. What
runs now is what has effectively been running all along: independent draws,
one parameter set per path, unbiased, with the tail precision the table
above says that buys.
"""

import math
import random

DEFAULT_PATHS = 20000


def _standard_t(rng, nu):
    """A Student-t draw standardised to unit variance."""
    # Ratio of a normal to the root of a scaled chi-square. The chi-square
    # is built from a gamma draw, which the standard library provides.
    z = rng.gauss(0.0, 1.0)
    chi2 = rng.gammavariate(nu / 2.0, 2.0)
    raw = z / math.sqrt(chi2 / nu)
    return raw * math.sqrt((nu - 2.0) / nu)


def simulate_paths(posterior, spot, horizon_days, paths=DEFAULT_PATHS,
                   seed=23):
    """Posterior predictive price paths.

    Returns the terminal prices, the per-day quantile fan, and the settings
    used. Every path is an independent draw, with its own posterior
    parameter set and its own shocks and nothing shared or mirrored between
    neighbours, so the requested count is generated exactly, less any path
    discarded as non-finite. The terminal list is sorted, for the readers
    that take quantiles and histograms from it; terminal_by_path keeps
    generation order, so the independence of consecutive paths can be
    measured rather than read off a flag.
    """
    if spot <= 0:
        raise ValueError("spot must be positive")
    if horizon_days < 1:
        raise ValueError("horizon must be at least one day")
    if paths < 1:
        raise ValueError("paths must be at least one")

    rng = random.Random(seed)
    draws = posterior.draws

    per_day = [[] for _ in range(horizon_days)]
    terminal = []
    discarded = 0
    # Independent draws. Each path takes its own parameter set, which is
    # what carries parameter uncertainty into the fan, and its own shocks,
    # drawn up front as one list so it is visible that nothing else feeds
    # the path. The pairing loop that stood here mirrored nothing, see the
    # module docstring: consecutive paths in generation order correlate at
    # -0.0032, and the test measures that rather than reading the
    # antithetic flag.
    for _ in range(paths):
        params = draws[rng.randrange(len(draws))]
        mu, omega, alpha, beta, nu = params
        if not all(math.isfinite(v) for v in params):
            discarded += 1
            continue
        base_variance = posterior.last_variance(params)
        if not math.isfinite(base_variance) or base_variance <= 0:
            discarded += 1
            continue
        shocks = [_standard_t(rng, nu) for _ in range(horizon_days)]
        variance = base_variance
        log_price = math.log(spot)
        path = []
        broken = False
        for day in range(horizon_days):
            residual = math.sqrt(variance) * shocks[day]
            log_price += mu + residual
            if not math.isfinite(log_price) or log_price > 700:
                broken = True
                break
            variance = (omega + alpha * residual * residual
                        + beta * variance)
            path.append(math.exp(log_price))
        if broken or len(path) != horizon_days:
            discarded += 1
            continue
        for day, price in enumerate(path):
            per_day[day].append(price)
        terminal.append(path[-1])

    if not terminal:
        raise ValueError(
            "every simulated path was discarded as non-finite. The "
            "posterior is unusable, which usually means the returns fed to "
            "the sampler contained a NaN or an infinity.")

    quantiles = (0.05, 0.25, 0.50, 0.75, 0.95)
    fan = []
    for day, values in enumerate(per_day, start=1):
        values.sort()
        row = {"day": day}
        for q in quantiles:
            row["p{}".format(int(q * 100))] = _quantile(values, q)
        fan.append(row)

    by_path = list(terminal)
    terminal.sort()
    return {
        "terminal": terminal,
        "terminal_by_path": by_path,
        "fan": fan,
        "paths": len(terminal),
        "requested_paths": paths,
        "discarded_paths": discarded,
        "horizon_days": horizon_days,
        "spot": spot,
        # False, and stated rather than removed, because every artifact
        # written before this said true and a reader comparing two runs
        # needs to see the field change rather than vanish.
        "antithetic": False,
        "quantiles": list(quantiles),
        "note": ("Paths are independent draws, one posterior "
                 "parameter set each, so parameter uncertainty is "
                 "carried into the fan rather than collapsed to a "
                 "point estimate. Earlier runs of this tool "
                 "reported antithetic pairs; the mirroring was "
                 "measured to be inert and has been removed."),
    }


def _quantile(sorted_values, fraction):
    if not sorted_values:
        return None
    position = fraction * (len(sorted_values) - 1)
    lower = int(math.floor(position))
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = position - lower
    return (sorted_values[lower] * (1.0 - weight)
            + sorted_values[upper] * weight)


def terminal_risk(simulation, levels=(0.95, 0.99)):
    """Value at risk and expected shortfall on the horizon return.

    Both are stated as losses on the underlying, positive numbers meaning a
    loss. Expected shortfall is the mean of the tail beyond the value at
    risk, which is the number that says how bad the bad case is rather than
    merely where it starts.
    """
    terminal = simulation["terminal"]
    spot = simulation["spot"]
    if not terminal:
        return None
    returns = sorted(price / spot - 1.0 for price in terminal)

    # probability_up counted "r > 0", which is False for NaN, so a run of
    # NaN returns reported a clean zero. Non-finite returns are refused.
    if not all(math.isfinite(r) for r in returns):
        return None

    out = {"horizon_days": simulation["horizon_days"],
           "paths": simulation["paths"],
           "mean_return": sum(returns) / len(returns),
           "median_return": _quantile(returns, 0.5),
           "probability_up": sum(1 for r in returns if r > 0) / len(returns),
           "insufficient_paths": []}
    for level in levels:
        label = int(round(level * 10000)) / 100.0
        key = ("{:g}".format(label)).replace(".", "_")
        index = max(0, int(math.floor((1.0 - level) * len(returns))) - 1)
        var_return = returns[index]
        tail = returns[:index + 1] or [var_return]
        # With too few paths the index floors onto the single worst one and
        # value at risk equals expected shortfall exactly, which looks like
        # a number and is not one.
        if len(tail) < 2:
            out["insufficient_paths"].append(
                "{} paths cannot estimate a {:g} percent level: the tail "
                "holds {} path".format(len(returns), level * 100, len(tail)))
        out["var_{}".format(key)] = -var_return
        out["es_{}".format(key)] = -(sum(tail) / len(tail))
    out["note"] = ("Value at risk and expected shortfall are on the "
                   "underlying's return over the horizon, expressed as "
                   "positive losses, from the posterior predictive "
                   "distribution. They are model output, not a limit and "
                   "not a promise about the worst case.")
    return out


def position_distribution(simulation, pnl_at_price):
    """Distribution of a position's profit across the simulated terminals.

    pnl_at_price maps a settlement price to a profit, which is exactly what
    the payoff engine provides, so a structure's whole distribution comes
    from the same paths as the underlying's.
    """
    terminal = simulation["terminal"]
    if not terminal:
        return None
    outcomes = sorted(pnl_at_price(price) for price in terminal)
    n = len(outcomes)
    losses = [v for v in outcomes if v < 0]
    tail_index = max(0, int(math.floor(0.05 * n)) - 1)
    tail = outcomes[:tail_index + 1] or [outcomes[0]]

    histogram = _histogram(outcomes, bins=40)
    return {
        "paths": n,
        "mean": sum(outcomes) / n,
        "median": _quantile(outcomes, 0.5),
        "p5": _quantile(outcomes, 0.05),
        "p25": _quantile(outcomes, 0.25),
        "p75": _quantile(outcomes, 0.75),
        "p95": _quantile(outcomes, 0.95),
        "probability_of_profit": sum(1 for v in outcomes if v > 0) / n,
        "probability_of_loss": len(losses) / n,
        "expected_loss_given_loss": (sum(losses) / len(losses)
                                     if losses else 0.0),
        "expected_shortfall_5": sum(tail) / len(tail),
        "worst": outcomes[0],
        "best": outcomes[-1],
        "histogram": histogram,
        "note": ("Profit distribution under the posterior predictive paths, "
                 "priced at expiry from the structure's own legs. It uses "
                 "the volatility the underlying has actually shown, not the "
                 "volatility the options are priced at, so it will disagree "
                 "with the model probabilities on the plan and that "
                 "disagreement is the point."),
    }


def _histogram(sorted_values, bins=40):
    low, high = sorted_values[0], sorted_values[-1]
    if high <= low:
        return [{"lo": low, "hi": high, "count": len(sorted_values)}]
    width = (high - low) / bins
    counts = [0] * bins
    for value in sorted_values:
        index = min(bins - 1, int((value - low) / width))
        counts[index] += 1
    return [{"lo": low + i * width, "hi": low + (i + 1) * width,
             "count": counts[i]} for i in range(bins)]
