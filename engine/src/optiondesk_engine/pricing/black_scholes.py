"""European Black-Scholes-Merton pricing and implied volatility.

Copyright (C) 2026 Iman Samizadeh. Licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate written agreement. See the
LICENSE file at the root of the engine component.

Derived from the author's prior work in the 001-qaunt repository
(smartsheep.witty.models.pricing) and relicensed here by the copyright
holder. See THIRD-PARTY.md.

Conventions used throughout the engine, stated once here because a wrong
convention is the most common source of a wrong Greek:

  t       time to expiry in YEARS, ACT/365 (calendar days / 365)
  sigma   volatility per 1.00, so 0.20 is 20 percent, never 20
  r       continuously compounded risk-free rate per 1.00
  q       continuous dividend yield per 1.00, 0.0 for a non-payer
  kind    the string "call" or "put", never a boolean flag

Prices are theoretical model values. They are not quotes and not fills.
"""

import math

DEFAULT_R = 0.04
DEFAULT_Q = 0.0
DAYS_PER_YEAR = 365.0

_SQRT_2PI = math.sqrt(2.0 * math.pi)
_SQRT_2 = math.sqrt(2.0)

# Bounds on any implied volatility this module will return. A solver that
# wanders outside these has not found a volatility, it has found a bad
# quote, and returning None is the honest answer.
IV_MIN = 0.001
IV_MAX = 5.0

# Below this sensitivity a price says nothing about volatility.
#
# The solver accepts a candidate when the model reprices within tol. For a
# contract whose value barely moves with volatility, that test is satisfied
# by the seed itself, and by every other volatility in the range: the price
# simply does not identify one. Requiring a minimum vega turns that from a
# fabricated answer into an honest refusal.
#
# The number is derived, not chosen: to distinguish volatilities half a
# point apart at a price tolerance of tol, the price must move by more than
# tol over that half point, so vega must exceed tol / 0.005.
#
# Vega is that requirement linearised at one point, and one point is not
# enough. The model price is convex in volatility deep in and out of the
# money, so a root can sit where vega has just climbed above the threshold
# while the price is flat, within tol, all the way down to IV_MIN. The
# solver then returns the top edge of that band. Measured on a grid of
# 1440 contracts: 43 priced within 1e-6 of the intrinsic floor came back
# 0.001 to 0.07 above the truth with vega at the answer 2.0e-4 to 7.8e-4,
# and the worst, a put at S=50 K=90 T=1 true volatility 0.05, came back as
# 0.117513 with vega 2.6e-27 at the truth. So _accept also applies the
# requirement exactly, in both directions: a step of SIGMA_RESOLUTION
# either way from the answer has to take the model price out of the
# tolerance band. One direction is not enough either: at that worst case
# the step up moves the price by 2.8e-6, more than tol, and the step down
# by 3e-7.
SIGMA_RESOLUTION = 0.005
MIN_VEGA = 1e-6 / SIGMA_RESOLUTION


def _pdf(x):
    """Standard normal density."""
    return math.exp(-0.5 * x * x) / _SQRT_2PI


def _cdf(x):
    """Standard normal cumulative distribution."""
    return 0.5 * (1.0 + math.erf(x / _SQRT_2))


# Plausibility ceilings. These exist to catch unit errors, which this
# module's own documentation calls the most common source of a wrong
# answer: volatility given as 20 instead of 0.20, time given in days
# instead of years, a rate given as 5 instead of 0.05. Each of those
# produces a complete, finite, entirely wrong Greek ladder with no
# complaint, so the complaint is added here. The limits are far outside any
# real market: 1000 percent volatility, a century to expiry.
MAX_SIGMA = 10.0
MAX_YEARS = 100.0


def _validate(spot, strike, t, sigma, kind):
    if kind not in ("call", "put"):
        raise ValueError("kind must be 'call' or 'put', got {!r}".format(kind))
    if spot <= 0 or strike <= 0 or t <= 0 or sigma <= 0:
        raise ValueError("spot, strike, t and sigma must all be > 0")
    if sigma > MAX_SIGMA:
        raise ValueError(
            "sigma is {:g}, above the plausibility ceiling of {:g}. "
            "Volatility is per 1.00, so 20 percent is 0.20, not 20."
            .format(sigma, MAX_SIGMA))
    if t > MAX_YEARS:
        raise ValueError(
            "t is {:g} years, above the plausibility ceiling of {:g}. "
            "Time is in years, so 30 days is 30/365, not 30."
            .format(t, MAX_YEARS))


def d1_d2(spot, strike, t, sigma, r=DEFAULT_R, q=DEFAULT_Q):
    """The two Black-Scholes arguments, shared by price and every Greek."""
    sq = sigma * math.sqrt(t)
    d1 = (math.log(spot / strike) + (r - q + 0.5 * sigma * sigma) * t) / sq
    return d1, d1 - sq


def bs_price(spot, strike, t, sigma, kind, r=DEFAULT_R, q=DEFAULT_Q):
    """Black-Scholes-Merton price of a European option.

    This is the function the finite-difference tests differentiate, so the
    analytic Greeks in greeks_full are checked against this exact
    implementation rather than against a second, subtly different one.
    """
    _validate(spot, strike, t, sigma, kind)
    d1, d2 = d1_d2(spot, strike, t, sigma, r, q)
    disc = math.exp(-r * t)
    carry = math.exp(-q * t)
    if kind == "call":
        value = spot * carry * _cdf(d1) - strike * disc * _cdf(d2)
    else:
        value = strike * disc * _cdf(-d2) - spot * carry * _cdf(-d1)
    # Deep out of the money, the two terms are nearly equal and their
    # difference underflows to a value like -4e-15. A European option
    # cannot be worth less than nothing, and a negative price propagates
    # into elasticity and into any artifact that prints it, so the
    # cancellation noise is floored here rather than downstream.
    return value if value > 0.0 else 0.0


def vega_raw(spot, strike, t, sigma, r=DEFAULT_R, q=DEFAULT_Q):
    """dV/dsigma per 1.00 of volatility. Used by the IV solver."""
    _validate(spot, strike, t, sigma, "call")
    d1, _ = d1_d2(spot, strike, t, sigma, r, q)
    return spot * math.exp(-q * t) * _pdf(d1) * math.sqrt(t)


def intrinsic(spot, strike, kind, t=0.0, r=DEFAULT_R, q=DEFAULT_Q):
    """Discounted intrinsic value, the no-arbitrage floor for a European
    option. Used to reject quotes that cannot imply any volatility."""
    disc = math.exp(-r * t)
    carry = math.exp(-q * t)
    if kind == "call":
        return max(spot * carry - strike * disc, 0.0)
    return max(strike * disc - spot * carry, 0.0)


def implied_vol(price, spot, strike, t, kind, r=DEFAULT_R, q=DEFAULT_Q,
                tol=1e-6, max_iter=60):
    """Implied volatility from an option price, or None.

    Newton-Raphson from a 0.30 seed, falling back to bisection when Newton
    leaves the bracket, stalls, runs out of iterations, or reaches a point
    where the price is locally insensitive to volatility.

    A candidate is accepted only when the price both reprices within tol AND
    is actually sensitive to volatility there, meaning vega exceeds
    MIN_VEGA and, exactly rather than linearised, that moving the candidate
    by SIGMA_RESOLUTION in either direction takes the model price outside
    the tolerance band. Without the second test the seed itself satisfies
    the first for any contract whose value is dominated by intrinsic, and
    the function returns 0.30 for a contract whose true volatility is 0.05,
    0.10, 0.20 or anything else. Without the third it returns the top edge
    of a band of volatilities that all reprice the quote, which is the
    same failure with a different number. That is the exact failure this
    module tells its callers to avoid, committed by the solver rather than
    by them. A returned volatility is therefore within SIGMA_RESOLUTION of
    every volatility that reprices the quote, the truth included.

    Returns None rather than a number whenever the input cannot imply a
    volatility: a non-positive price, an expired contract, a quote below
    discounted intrinsic, a price that does not identify a volatility, or a
    solve that will not converge inside [IV_MIN, IV_MAX]. Downstream code
    must skip those contracts and must never substitute a default, because a
    guessed volatility produces a complete and entirely fictional Greek
    ladder that looks exactly as authoritative as a real one.
    """
    if price is None or price <= 0 or t <= 0 or spot <= 0 or strike <= 0:
        return None
    if kind not in ("call", "put"):
        return None
    if price < intrinsic(spot, strike, kind, t, r, q) - tol:
        return None

    sigma = 0.30
    for _ in range(max_iter):
        try:
            est = bs_price(spot, strike, t, sigma, kind, r, q)
            v = vega_raw(spot, strike, t, sigma, r, q)
        except (ValueError, ZeroDivisionError, OverflowError):
            break
        diff = est - price
        if abs(diff) < tol:
            return _accept(sigma, price, spot, strike, t, kind, r, q, tol)
        if abs(v) < MIN_VEGA:
            # Newton has nowhere to go from HERE. That is a statement about
            # this iterate, not about the contract, and treating it as a
            # refusal was wrong: vega is evaluated at the 0.30 seed, and a
            # deep in the money contract has almost no vega there while
            # having plenty at its actual volatility. An audit measured the
            # cost on one live SPY chain: 41 of 56 refusals were solvable by
            # bisection to better than 1e-5 in sigma, with vega at the
            # answer between 0.26 and 6.5, and the resulting fallback to
            # provider volatility was the sole reason the chain and its
            # ladder were both marked degraded.
            #
            # Bisection is bracketed and cannot diverge, and _accept still
            # tests vega AT THE ANSWER, which is where the identification
            # question belongs. A contract that genuinely carries no
            # volatility information is still refused there.
            break
        sigma -= diff / v
        if not (IV_MIN < sigma <= IV_MAX):
            break

    # Falling out of the loop means Newton either left the bracket or
    # exhausted its iterations. Both go to the bracketed solver; neither
    # returns the last iterate, which would publish an unconverged guess to
    # six decimal places.
    return _bisect_iv(price, spot, strike, t, kind, r, q, tol, max_iter)


def _accept(sigma, price, spot, strike, t, kind, r, q, tol):
    """Return sigma only if it is inside the range and identified.

    Identified means vega above MIN_VEGA at the answer, which is the
    linearised test, and the exact test behind it: the quote pins the
    volatility to within SIGMA_RESOLUTION on both sides. See the note at
    MIN_VEGA for the measurement that made the second one necessary.
    """
    if not (IV_MIN < sigma <= IV_MAX):
        return None
    try:
        if abs(vega_raw(spot, strike, t, sigma, r, q)) < MIN_VEGA:
            return None
        if not _pinned(sigma, price, spot, strike, t, kind, r, q, tol):
            return None
    except (ValueError, ZeroDivisionError, OverflowError):
        return None
    return round(sigma, 6)


def _pinned(sigma, price, spot, strike, t, kind, r, q, tol):
    """True when every volatility that reprices the quote within tol lies
    within SIGMA_RESOLUTION of sigma.

    The model price rises with volatility, so one step either side is
    enough to look: if the price a resolution step away is already outside
    the tolerance band, nothing further out can be inside it. A step that
    would leave [IV_MIN, IV_MAX] is not taken, because the edge of the
    range bounds the band by itself and is within a step of sigma.
    """
    above = sigma + SIGMA_RESOLUTION
    if above < IV_MAX:
        if bs_price(spot, strike, t, above, kind, r, q) <= price + tol:
            return False
    below = sigma - SIGMA_RESOLUTION
    if below > IV_MIN:
        if bs_price(spot, strike, t, below, kind, r, q) >= price - tol:
            return False
    return True


def _bisect_iv(price, spot, strike, t, kind, r, q, tol, max_iter):
    """Bracketed fallback. Slower than Newton, but it cannot diverge."""
    lo, hi = IV_MIN, IV_MAX
    try:
        p_lo = bs_price(spot, strike, t, lo, kind, r, q)
        p_hi = bs_price(spot, strike, t, hi, kind, r, q)
    except (ValueError, ZeroDivisionError, OverflowError):
        return None
    if not (p_lo - tol <= price <= p_hi + tol):
        return None
    for _ in range(max_iter * 2):
        mid = 0.5 * (lo + hi)
        try:
            p_mid = bs_price(spot, strike, t, mid, kind, r, q)
        except (ValueError, ZeroDivisionError, OverflowError):
            return None
        if abs(p_mid - price) < tol:
            return _accept(mid, price, spot, strike, t, kind, r, q, tol)
        if p_mid < price:
            lo = mid
        else:
            hi = mid
    return _accept(0.5 * (lo + hi), price, spot, strike, t, kind, r, q, tol)
