"""Complete analytic Black-Scholes-Merton Greek ladder, first to third order.

Copyright (C) 2026 Iman Samizadeh. Licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate written agreement.

Derived from the author's prior work in the 001-qaunt repository
(smartsheep.witty.models.pricing.greeks_full) and relicensed here by the
copyright holder, extended to carry a continuous dividend yield q so the
same ladder serves equity index ETFs, single names that pay a dividend, and
later Black-76 style carry cases.

Every quantity below is verified against a central finite difference of
black_scholes.bs_price in the test suite. That matters more than the
formulas being quotable: an analytic Greek that disagrees with the price
function it claims to differentiate is worse than no Greek at all, because
it looks authoritative.

UNITS. These are the second most common source of a wrong answer, after
volatility given in percent. Stated once, and repeated in the artifact
schema so a consumer never has to guess:

  price       model value in the underlying's quote currency
  delta       dV/dS, per 1.0 of underlying move
  gamma       d2V/dS2, delta change per 1.0 of underlying move
  vega        dV/dsigma, per 1.00 of volatility. Divide by 100 for the
              conventional "per volatility point" figure
  theta       dV/dt per CALENDAR DAY of time passing. Negative means decay
  rho         dV/dr, per 1.00 of rate
  lam         elasticity, delta * S / V, dimensionless
  vanna       d2V/dS dsigma
  vomma       d2V/dsigma2, also called volga
  charm       delta change per CALENDAR DAY of time passing
  veta        vega change per CALENDAR DAY of time passing
  speed       d3V/dS3, gamma change per 1.0 of underlying move
  zomma       dGamma/dsigma
  color       gamma change per CALENDAR DAY of time passing
  ultima      d3V/dsigma3
  dual_delta  dV/dK
  dual_gamma  d2V/dK2

The four per-day quantities (theta, charm, veta, color) are all expressed
with the same sign convention: the change in the quantity as one calendar
day passes, which is the negative of the derivative with respect to time
remaining, divided by 365.
"""

import math

from optiondesk_engine.pricing.black_scholes import (
    DAYS_PER_YEAR,
    DEFAULT_Q,
    DEFAULT_R,
    _cdf,
    _pdf,
    _validate,
    d1_d2,
)

GREEK_KEYS = (
    "delta", "gamma", "vega", "theta", "rho", "lam",
    "vanna", "vomma", "charm", "veta",
    "speed", "zomma", "color", "ultima",
    "dual_delta", "dual_gamma",
)

# The subset that nets meaningfully across the legs of a spread. Summing
# elasticity or the dual Greeks across legs produces a number with no
# interpretation, so they are deliberately absent.
NET_KEYS = ("delta", "gamma", "vega", "theta", "rho",
            "vanna", "vomma", "charm", "veta")


def all_greeks(spot, strike, t, sigma, kind, r=DEFAULT_R, q=DEFAULT_Q):
    """Full analytic Greek ladder for one European contract.

    t is in years (ACT/365), sigma is per 1.00, kind is "call" or "put".
    Returns a dict with "price" plus every key in GREEK_KEYS.

    Raises ValueError on inputs that cannot produce a ladder rather than
    returning zeros, because a zero Greek and an unknown Greek mean very
    different things to a risk gate downstream.
    """
    _validate(spot, strike, t, sigma, kind)

    sqt = math.sqrt(t)
    sq = sigma * sqt
    d1, d2 = d1_d2(spot, strike, t, sigma, r, q)
    pdf1 = _pdf(d1)
    disc = math.exp(-r * t)
    carry = math.exp(-q * t)

    # first order
    gamma = carry * pdf1 / (spot * sq)
    vega = spot * carry * pdf1 * sqt

    if kind == "call":
        price = spot * carry * _cdf(d1) - strike * disc * _cdf(d2)
        delta = carry * _cdf(d1)
        theta_year = (-spot * carry * pdf1 * sigma / (2.0 * sqt)
                      + q * spot * carry * _cdf(d1)
                      - r * strike * disc * _cdf(d2))
        rho = strike * t * disc * _cdf(d2)
        dual_delta = -disc * _cdf(d2)
        charm_year = (q * carry * _cdf(d1)
                      - carry * pdf1 * ((r - q) / sq - d2 / (2.0 * t)))
    else:
        price = strike * disc * _cdf(-d2) - spot * carry * _cdf(-d1)
        delta = carry * (_cdf(d1) - 1.0)
        theta_year = (-spot * carry * pdf1 * sigma / (2.0 * sqt)
                      - q * spot * carry * _cdf(-d1)
                      + r * strike * disc * _cdf(-d2))
        rho = -strike * t * disc * _cdf(-d2)
        dual_delta = disc * _cdf(-d2)
        charm_year = (-q * carry * _cdf(-d1)
                      - carry * pdf1 * ((r - q) / sq - d2 / (2.0 * t)))

    # second order, identical for calls and puts
    vanna = -carry * pdf1 * d2 / sigma
    vomma = vega * d1 * d2 / sigma
    veta_year = vega * (q + (r - q) * d1 / sq - (1.0 + d1 * d2) / (2.0 * t))

    # third order
    speed = -gamma / spot * (d1 / sq + 1.0)
    zomma = gamma * (d1 * d2 - 1.0) / sigma
    color_year = gamma * (q + (r - q) * d1 / sq
                          + (1.0 - d1 * d2) / (2.0 * t))
    ultima = (-vega / (sigma * sigma)
              * (d1 * d2 * (1.0 - d1 * d2) + d1 * d1 + d2 * d2))
    dual_gamma = disc * _pdf(d2) / (strike * sq)

    # Elasticity is undefined for a worthless option. Zero is returned as
    # the neutral value, and the price is carried alongside so a consumer
    # can tell "no leverage" from "no value".
    lam = delta * spot / price if price > 0 else 0.0

    return {
        "price": price,
        "delta": delta,
        "gamma": gamma,
        "vega": vega,
        "theta": theta_year / DAYS_PER_YEAR,
        "rho": rho,
        "lam": lam,
        "vanna": vanna,
        "vomma": vomma,
        "charm": charm_year / DAYS_PER_YEAR,
        "veta": veta_year / DAYS_PER_YEAR,
        "speed": speed,
        "zomma": zomma,
        "color": color_year / DAYS_PER_YEAR,
        "ultima": ultima,
        "dual_delta": dual_delta,
        "dual_gamma": dual_gamma,
    }


def net_greeks(legs):
    """Net the Greeks of a multi-leg position.

    legs is an iterable of (greeks_dict, signed_quantity), where quantity is
    positive for long and negative for short, in contracts. Only NET_KEYS
    are summed. The caller applies any contract multiplier; this function
    stays in per-contract units so it cannot silently double-apply a 100x.

    A leg missing a Greek is counted, not treated as zero. Summing a missing
    delta as zero halves the reported exposure of a two-leg position and
    returns it as an ordinary number, which is indistinguishable from a
    genuinely small exposure. The counts are returned alongside so a caller
    can refuse to act on a partial total.
    """
    out = {key: 0.0 for key in NET_KEYS}
    missing = {key: 0 for key in NET_KEYS}
    legs_counted = 0
    for greeks, qty in legs:
        legs_counted += 1
        for key in NET_KEYS:
            value = greeks.get(key)
            if value is None:
                missing[key] += 1
                continue
            out[key] += float(value) * float(qty)
    out["legs"] = legs_counted
    out["missing"] = {key: count for key, count in missing.items() if count}
    out["complete"] = not out["missing"]
    return out
