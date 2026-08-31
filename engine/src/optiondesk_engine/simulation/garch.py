"""GARCH(1,1) with Student-t innovations, estimated by MCMC.

Copyright (C) 2026 Iman Samizadeh. Licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate written agreement.
Follows the Bayesian GARCH-t work in the author's 001-qaunt desk
(smartsheep.witty.models.stochastic), reimplemented here in the standard
library so the engine keeps its no-dependency property.

THE MODEL

    r_t     = mu + e_t
    e_t     = sigma_t * z_t,     z_t ~ standardised Student-t with nu df
    sigma_t^2 = omega + alpha * e_{t-1}^2 + beta * sigma_{t-1}^2

Student-t rather than normal because equity returns have fatter tails than
a normal admits, and a model that cannot produce the tail will price the
tail at zero. The innovation is standardised to unit variance so sigma
remains interpretable as a volatility rather than absorbing a scale factor
from the degrees of freedom.

WHY MCMC RATHER THAN MAXIMUM LIKELIHOOD

A point estimate of alpha and beta hides how uncertain they are, and that
uncertainty dominates a forecast at the horizons this desk cares about.
The posterior carries it: simulating with a draw per path propagates
parameter uncertainty into the fan, where a single fitted parameter set
would produce a fan that is too narrow and a value at risk that is too
comfortable.

DIAGNOSTICS ARE NOT OPTIONAL

Two chains from different starting points, split R-hat and effective sample
size per parameter, and an acceptance rate. A posterior that has not
converged is reported as not converged rather than summarised as though it
had.
"""

import math
import random

DEFAULT_DRAWS = 3000
DEFAULT_BURN = 1000
DEFAULT_CHAINS = 2

# Above this, the chains disagree enough that the summary is not a summary
# of anything. The conventional threshold.
RHAT_LIMIT = 1.05
MIN_ESS = 100


def _lgamma(x):
    return math.lgamma(x)


def garch_log_likelihood(returns, mu, omega, alpha, beta, nu):
    """Log likelihood of the GARCH(1,1)-t model, or negative infinity.

    Returns negative infinity for any parameter set outside the region
    where the model is defined: non-positive variance parameters, a
    non-stationary alpha plus beta, or degrees of freedom at or below two,
    where the t distribution has no finite variance to standardise.
    """
    if omega <= 0 or alpha < 0 or beta < 0 or alpha + beta >= 1 or nu <= 2.0:
        return float("-inf")
    n = len(returns)
    if n < 10:
        return float("-inf")

    scale = math.sqrt((nu - 2.0) / nu)
    constant = (_lgamma((nu + 1.0) / 2.0) - _lgamma(nu / 2.0)
                - 0.5 * math.log(math.pi * nu))

    # Start the recursion at the unconditional variance, which is the
    # stationary distribution of the process rather than an arbitrary seed.
    variance = omega / (1.0 - alpha - beta)
    total = 0.0
    for value in returns:
        if variance <= 0:
            return float("-inf")
        residual = value - mu
        standardised = residual / (math.sqrt(variance) * scale)
        total += (constant - 0.5 * math.log(variance) - math.log(scale)
                  - (nu + 1.0) / 2.0
                  * math.log1p(standardised * standardised / nu))
        variance = omega + alpha * residual * residual + beta * variance
    return total


# THE PARAMETERISATION MATTERS MORE THAN THE SAMPLER.
#
# Sampling omega directly mixes badly, because omega and beta are strongly
# correlated by construction: raising persistence while lowering the
# intercept leaves the fitted variance path almost unchanged, so the
# posterior is a long thin ridge and a coordinate-wise sampler crawls along
# it.
#
# Sampling the UNCONDITIONAL variance instead REDUCES that correlation.
# It does not remove it, and an earlier version of this comment claimed it
# did. Measured against a second sampler written in the direct coordinates
# with a numerical Jacobian, both targeting the same posterior: the
# correlation between the two sampled variance coordinates falls from
# -0.84 to +0.67, and effective sample size on omega, alpha and beta rises
# by a factor of 10 to 17. The posterior's own correlation between omega
# and beta is about -0.80 and no choice of coordinates changes it.
#
# omega is derived:
#
#     omega = unconditional_variance * (1 - alpha - beta)
#
# Priors are specified directly on these unconstrained coordinates, which is
# a deliberate choice rather than an omitted Jacobian: it makes the prior
# something a reader can see and argue with in the space where the sampling
# happens.

def _to_unconstrained(params):
    mu, omega, alpha, beta, nu = params
    persistence = alpha + beta
    unconditional = omega / (1.0 - persistence)
    share = alpha / persistence
    return [
        mu,
        math.log(unconditional),
        math.log(persistence / (1.0 - persistence)),
        math.log(share / (1.0 - share)),
        math.log(nu - 2.0),
    ]


def _from_unconstrained(vector):
    mu, log_variance, logit_persistence, logit_share, log_nu = vector
    persistence = 1.0 / (1.0 + math.exp(-logit_persistence))
    share = 1.0 / (1.0 + math.exp(-logit_share))
    alpha = persistence * share
    beta = persistence - alpha
    omega = math.exp(log_variance) * (1.0 - persistence)
    return [mu, omega, alpha, beta, math.exp(log_nu) + 2.0]


def _log_posterior(vector, returns, variance_hint):
    params = _from_unconstrained(vector)
    likelihood = garch_log_likelihood(returns, *params)
    if likelihood == float("-inf"):
        return float("-inf")

    mu, _, _, _, nu = params
    log_variance, logit_persistence, logit_share, log_nu = vector[1:]
    # Weak, stated priors. Persistence near 0.9 and an alpha share near 0.12
    # are what equity index returns almost always show; the widths are loose
    # enough that several hundred observations dominate them.
    prior = (
        -0.5 * (mu / 0.05) ** 2
        - 0.5 * ((log_variance - math.log(variance_hint)) / 2.0) ** 2
        - 0.5 * ((logit_persistence - 2.2) / 1.5) ** 2
        - 0.5 * ((logit_share + 2.0) / 1.5) ** 2
        - 0.5 * ((log_nu - math.log(6.0)) / 1.0) ** 2
    )
    return likelihood + prior


def _percentile(sorted_values, fraction):
    if not sorted_values:
        return None
    position = fraction * (len(sorted_values) - 1)
    lower = int(math.floor(position))
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = position - lower
    return (sorted_values[lower] * (1.0 - weight)
            + sorted_values[upper] * weight)


def _split_rhat(chains):
    """Split R-hat: each chain halved, so a drifting chain is caught.

    Returns None only when the halves cannot be compared at all. A zero
    within-chain variance means the sampler never moved, which is a
    catastrophic failure rather than perfect agreement, so it returns
    infinity and fails the gate.
    """
    halves = []
    for chain in chains:
        middle = len(chain) // 2
        halves.append(chain[:middle])
        halves.append(chain[middle:2 * middle])
    halves = [h for h in halves if len(h) > 1]
    if len(halves) < 2:
        return None
    n = min(len(h) for h in halves)
    halves = [h[:n] for h in halves]
    m = len(halves)
    means = [sum(h) / n for h in halves]
    grand = sum(means) / m
    between = n / (m - 1.0) * sum((mean - grand) ** 2 for mean in means)
    within_each = [sum((v - mean) ** 2 for v in h) / (n - 1.0)
                   for h, mean in zip(halves, means)]
    within = sum(within_each) / m
    if within <= 0:
        # Every draw identical: the chain is stuck, not converged.
        return float("inf")
    variance = (n - 1.0) / n * within + between / n
    return math.sqrt(variance / within)


def _ess(chain):
    """Effective sample size from the autocorrelation sum.

    Two honest limitations, stated because the number is published as a
    quality figure. Truncating the sum at the first autocorrelation below
    0.05 discards a positive tail, which INFLATES the estimate for a badly
    mixing chain: measured against an AR(1) with known answer, an ESS
    reported as 13 can correspond to a true 1.5. Treat any value below
    about 30 from this estimator as unreliable. Near the gate of 100 the
    overstatement measured 2 to 6 percent.

    A chain with zero variance has an effective sample size of one, not of
    n: it carries a single point repeated.
    """
    n = len(chain)
    if n < 10:
        return float(n)
    mean = sum(chain) / n
    centred = [v - mean for v in chain]
    variance = sum(v * v for v in centred) / n
    if variance <= 0:
        return 1.0
    total = 0.0
    for lag in range(1, min(n // 2, 200)):
        covariance = sum(centred[i] * centred[i + lag]
                         for i in range(n - lag)) / n
        rho = covariance / variance
        if rho < 0.05:
            break
        total += rho
    return n / (1.0 + 2.0 * total)


class GarchPosterior:
    """Posterior draws plus the diagnostics needed to trust them."""

    NAMES = ("mu", "omega", "alpha", "beta", "nu")

    def __init__(self, draws, diagnostics, returns):
        self.draws = draws
        self.diagnostics = diagnostics
        self.returns = returns

    @property
    def converged(self):
        return self.diagnostics["converged"]

    def summary(self):
        out = {}
        for index, name in enumerate(self.NAMES):
            values = sorted(draw[index] for draw in self.draws)
            out[name] = {
                "mean": sum(values) / len(values),
                "p5": _percentile(values, 0.05),
                "p50": _percentile(values, 0.50),
                "p95": _percentile(values, 0.95),
                "rhat": self.diagnostics["rhat"].get(name),
                "ess": self.diagnostics["ess"].get(name),
            }
        return out

    def last_variance(self, params):
        """Conditional variance for the next step under one draw."""
        mu, omega, alpha, beta, _ = params
        variance = omega / (1.0 - alpha - beta)
        for value in self.returns:
            residual = value - mu
            variance = omega + alpha * residual * residual + beta * variance
        return variance


def fit_garch_t(returns, draws=DEFAULT_DRAWS, burn=DEFAULT_BURN,
                chains=DEFAULT_CHAINS, seed=11):
    """Sample the posterior of a GARCH(1,1)-t model by adaptive random walk.

    Returns a GarchPosterior. Convergence is reported, never assumed: if
    split R-hat exceeds its limit or effective sample size is too small for
    any parameter, converged is False and the caller is expected to say so
    rather than quoting the quantiles as though they meant something.
    """
    if len(returns) < 60:
        raise ValueError(
            "need at least 60 returns to estimate a GARCH model, got {}"
            .format(len(returns)))

    variance_hint = (sum(r * r for r in returns) / len(returns)) or 1e-6
    starts = [
        [0.0, variance_hint * 0.05, 0.08, 0.88, 7.0],
        [0.0005, variance_hint * 0.10, 0.15, 0.75, 12.0],
        [-0.0005, variance_hint * 0.02, 0.05, 0.92, 5.0],
    ]

    # Return scale sets the only step size that is not dimensionless: mu is
    # in return units while the rest are transformed to the whole line.
    return_scale = math.sqrt(variance_hint)

    all_chains = []
    accepted_total = proposed_total = 0
    # Reported separately from the burn-in figure: the rate during
    # adaptation describes a sampler that no longer exists.
    sampling_accepted = sampling_proposed = 0
    for chain_index in range(chains):
        rng = random.Random(seed + chain_index * 977)
        current = _to_unconstrained(starts[chain_index % len(starts)])
        current_lp = _log_posterior(current, returns,
                                    variance_hint)

        # One step size per coordinate, updated toward the acceptance rate
        # that is optimal for single-coordinate random-walk Metropolis. A
        # single joint proposal mixed at two percent here, because omega,
        # alpha and beta are strongly correlated and a joint step large
        # enough to move one is far too large for the others.
        step = [return_scale * 0.5, 0.15, 0.15, 0.15, 0.20]
        accepted = [0] * len(step)
        proposed = [0] * len(step)

        chain = []
        post_burn_accepted = 0
        post_burn_proposed = 0
        for iteration in range(draws + burn):
            for coordinate in range(len(current)):
                proposal = list(current)
                proposal[coordinate] += rng.gauss(0.0, step[coordinate])
                proposal_lp = _log_posterior(proposal, returns,
                                             variance_hint)
                proposed[coordinate] += 1
                proposed_total += 1
                if iteration >= burn:
                    post_burn_proposed += 1
                if (proposal_lp > current_lp
                        or math.log(rng.random() + 1e-300)
                        < proposal_lp - current_lp):
                    current, current_lp = proposal, proposal_lp
                    accepted[coordinate] += 1
                    accepted_total += 1
                    if iteration >= burn:
                        post_burn_accepted += 1

            # Adapt during burn-in only. Adapting afterwards would break the
            # Markov property and the draws would no longer be a posterior.
            if iteration < burn and iteration > 0 and iteration % 25 == 0:
                for coordinate in range(len(step)):
                    if not proposed[coordinate]:
                        continue
                    rate = accepted[coordinate] / float(proposed[coordinate])
                    if rate > 0.44:
                        step[coordinate] *= 1.25
                    elif rate < 0.20:
                        step[coordinate] *= 0.80
                accepted = [0] * len(step)
                proposed = [0] * len(step)

            if iteration >= burn:
                chain.append(_from_unconstrained(current))
        all_chains.append(chain)
        sampling_accepted += post_burn_accepted
        sampling_proposed += post_burn_proposed

    rhat = {}
    ess = {}
    for index, name in enumerate(GarchPosterior.NAMES):
        series = [[draw[index] for draw in chain] for chain in all_chains]
        rhat[name] = _split_rhat(series)
        ess[name] = min(_ess(s) for s in series)

    # A missing R-hat is not a pass. Neither is a sampler that never
    # accepted a proposal: an earlier version certified two chains parked
    # on the same point as converged with a perfect effective sample size.
    sampling_rate = (sampling_accepted / float(sampling_proposed)
                     if sampling_proposed else 0.0)
    converged = bool(sampling_rate > 0.0) and all(
        rhat[name] is not None
        and math.isfinite(rhat[name])
        and rhat[name] < RHAT_LIMIT
        and (ess[name] or 0) >= MIN_ESS
        for name in GarchPosterior.NAMES)

    diagnostics = {
        "chains": chains,
        "draws_per_chain": draws,
        "burn_in": burn,
        "acceptance_rate": sampling_rate,
        "acceptance_rate_including_burn_in": (accepted_total
                                             / float(proposed_total)),
        "rhat": rhat,
        "ess": ess,
        "converged": converged,
        "rhat_limit": RHAT_LIMIT,
        "min_ess": MIN_ESS,
        "note": ("Split R-hat above {} or effective sample size below {} on "
                 "any parameter means the chains have not agreed and the "
                 "quantiles should not be quoted. A zero acceptance rate "
                 "means the sampler never moved and nothing here is a "
                 "posterior. The effective sample size estimator truncates "
                 "its autocorrelation sum, which overstates for badly "
                 "mixing chains: below about 30 it should not be trusted."
                 .format(RHAT_LIMIT, MIN_ESS)),
    }
    flat = [draw for chain in all_chains for draw in chain]
    return GarchPosterior(flat, diagnostics, returns)
