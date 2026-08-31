"""Verify every analytic Greek against a central finite difference of the
price function it claims to differentiate, plus closed-form checks that do
not depend on the Greek code at all.

The finite-difference comparison is the point of this file. Any analytic
Greek can be transcribed with a sign error or a missing carry term and still
look plausible in a dashboard. Differentiating bs_price numerically is the
only cheap way to catch that.

Copyright (C) 2026 Iman Samizadeh. Licensed under the PolyForm Noncommercial License 1.0.0.
"""

import math

import pytest

from optiondesk_engine.pricing.black_scholes import (
    bs_price,
    implied_vol,
)
from optiondesk_engine.pricing.greeks_full import (
    GREEK_KEYS,
    all_greeks,
    net_greeks,
)

DAYS = 365.0

# spot, strike, t, sigma, r, q. Deliberately mixed: at the money, both
# wings, short and long dated, zero and non-zero dividend yield.
CASES = [
    (100.0, 100.0, 1.00, 0.20, 0.05, 0.00),
    (100.0, 100.0, 0.25, 0.35, 0.04, 0.02),
    (100.0, 120.0, 0.50, 0.25, 0.03, 0.01),
    (100.0, 80.0, 0.75, 0.30, 0.05, 0.03),
    (4500.0, 4600.0, 0.08, 0.18, 0.045, 0.015),
]
KINDS = ("call", "put")


def _fd(f, x, h):
    """Central first derivative."""
    return (f(x + h) - f(x - h)) / (2.0 * h)


def _fd2(f, x, h):
    """Central second derivative."""
    return (f(x + h) - 2.0 * f(x) + f(x - h)) / (h * h)


def _fd3(f, x, h):
    """Central third derivative."""
    return (f(x + 2 * h) - 2.0 * f(x + h)
            + 2.0 * f(x - h) - f(x - 2 * h)) / (2.0 * h ** 3)


def _close(actual, expected, tol, label):
    """Relative comparison, with no absolute floor.

    An earlier version scaled by max(1.0, |expected|), which silently turned
    every comparison on a quantity smaller than one into an absolute test.
    For color, whose value here is around 1e-6, a tolerance of 1e-2 was
    seven thousand times the number being checked: the test could not
    distinguish the correct value from zero, or from its own negation.
    Mutation testing found fourteen such blind spots, including a sign flip
    in exactly the Greek this file is credited with having caught.

    Values at true zero are compared absolutely against a floor small
    enough that a wrong sign or a dropped term still fails.
    """
    denominator = abs(expected)
    if denominator < 1e-12:
        assert abs(actual) <= 1e-10, (
            "{}: analytic {:.10g} where the finite difference is zero"
            .format(label, actual))
        return
    relative = abs(actual - expected) / denominator
    assert relative <= tol, (
        "{}: analytic {:.10g} vs finite difference {:.10g}, relative error "
        "{:.3g} exceeds {:g}".format(label, actual, expected, relative, tol))


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("kind", KINDS)
def test_price_matches_put_call_parity(case, kind):
    spot, strike, t, sigma, r, q = case
    call = bs_price(spot, strike, t, sigma, "call", r, q)
    put = bs_price(spot, strike, t, sigma, "put", r, q)
    lhs = call - put
    rhs = spot * math.exp(-q * t) - strike * math.exp(-r * t)
    assert abs(lhs - rhs) < 1e-9


def test_known_benchmark_value():
    # Textbook case: S=100, K=100, t=1, sigma=0.20, r=0.05, q=0.
    price = bs_price(100.0, 100.0, 1.0, 0.20, "call", 0.05, 0.0)
    assert abs(price - 10.450583572185565) < 1e-9
    greeks = all_greeks(100.0, 100.0, 1.0, 0.20, "call", 0.05, 0.0)
    assert abs(greeks["delta"] - 0.6368306511756191) < 1e-9
    assert abs(greeks["gamma"] - 0.018762017345846895) < 1e-9
    assert abs(greeks["vega"] - 37.52403469169379) < 1e-9


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("kind", KINDS)
def test_all_greeks_against_finite_difference(case, kind):
    spot, strike, t, sigma, r, q = case
    g = all_greeks(spot, strike, t, sigma, kind, r, q)

    # Steps are tuned per derivative order: the third-order and mixed
    # quantities need a wider step or truncation error swamps them, and
    # color needs a wider time step in particular.
    hs = spot * 1e-4
    hv = 1e-4
    ht = 3e-4
    hr = 1e-6
    hk = strike * 1e-4

    by_spot = lambda s: bs_price(s, strike, t, sigma, kind, r, q)
    by_vol = lambda v: bs_price(spot, strike, t, v, kind, r, q)
    by_time = lambda tt: bs_price(spot, strike, tt, sigma, kind, r, q)
    by_rate = lambda rr: bs_price(spot, strike, t, sigma, kind, rr, q)
    by_strike = lambda k: bs_price(spot, k, t, sigma, kind, r, q)

    _close(g["delta"], _fd(by_spot, spot, hs), 1e-6, "delta")
    _close(g["gamma"], _fd2(by_spot, spot, hs), 1e-5, "gamma")
    _close(g["vega"], _fd(by_vol, sigma, hv), 1e-6, "vega")
    _close(g["rho"], _fd(by_rate, r, hr), 1e-5, "rho")
    _close(g["dual_delta"], _fd(by_strike, strike, hk), 1e-6,
           "dual_delta")
    _close(g["dual_gamma"], _fd2(by_strike, strike, hk), 1e-5,
           "dual_gamma")

    # Per-day quantities: one calendar day of time passing is a decrease of
    # 1/365 in time remaining, so the analytic value is compared with
    # minus the derivative with respect to t, divided by 365.
    _close(g["theta"], -_fd(by_time, t, ht) / DAYS, 1e-5, "theta")

    # Cross and higher derivatives, built from the same price function.
    delta_of_vol = lambda v: _fd(
        lambda s: bs_price(s, strike, t, v, kind, r, q), spot, hs)
    _close(g["vanna"], _fd(delta_of_vol, sigma, hv), 1e-4, "vanna")
    _close(g["vomma"], _fd2(by_vol, sigma, hv), 1e-3, "vomma")

    delta_of_time = lambda tt: _fd(
        lambda s: bs_price(s, strike, tt, sigma, kind, r, q), spot, hs)
    _close(g["charm"], -_fd(delta_of_time, t, ht) / DAYS, 1e-4,
           "charm")

    # veta and color were both shipped with the wrong sign, and this
    # comparison is what caught them: veta came back as the positive
    # derivative of vega with respect to time rather than the negative, and
    # color the same for gamma. Nothing else would have found it. Both read
    # plausibly, both have the right magnitude, and a sign error in a
    # second-order Greek does not look wrong until it is differenced
    # against the price function it claims to differentiate.
    vega_of_time = lambda tt: _fd(
        lambda v: bs_price(spot, strike, tt, v, kind, r, q), sigma, hv)
    _close(g["veta"], -_fd(vega_of_time, t, ht) / DAYS, 1e-4, "veta")

    _close(g["speed"], _fd3(by_spot, spot, spot * 1e-3), 1e-3, "speed")

    gamma_of_vol = lambda v: _fd2(
        lambda s: bs_price(s, strike, t, v, kind, r, q), spot, hs)
    _close(g["zomma"], _fd(gamma_of_vol, sigma, hv), 1e-3, "zomma")

    # Color is a third derivative in mixed directions, so it needs a wider
    # spot step than the first-order Greeks: at hs the finite difference
    # itself is only accurate to about one part in a thousand, which is the
    # tolerance being tested. The analytic value is not the uncertain side
    # of this comparison.
    hs_color = spot * 3e-4
    gamma_of_time = lambda tt: _fd2(
        lambda s: bs_price(s, strike, tt, sigma, kind, r, q), spot, hs_color)
    _close(g["color"], -_fd(gamma_of_time, t, ht) / DAYS, 1e-3,
           "color")

    _close(g["ultima"], _fd3(by_vol, sigma, 1e-3), 1e-3, "ultima")

    # Elasticity has no finite difference of its own; it is checked against
    # its definition, which is the only thing that would catch it being
    # dropped, zeroed or sign-flipped.
    if g["price"] > 0:
        _close(g["lam"], g["delta"] * spot / g["price"], 1e-12, "lam")


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("kind", KINDS)
def test_ladder_is_complete_and_finite(case, kind):
    spot, strike, t, sigma, r, q = case
    g = all_greeks(spot, strike, t, sigma, kind, r, q)
    assert set(g) == set(GREEK_KEYS) | {"price"}
    for key, value in g.items():
        assert isinstance(value, float)
        assert math.isfinite(value), "{} is not finite".format(key)


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("kind", KINDS)
def test_implied_vol_round_trip(case, kind):
    spot, strike, t, sigma, r, q = case
    price = bs_price(spot, strike, t, sigma, kind, r, q)
    recovered = implied_vol(price, spot, strike, t, kind, r, q)
    assert recovered is not None
    assert abs(recovered - sigma) < 1e-4


def test_implied_vol_refuses_impossible_inputs():
    # Below discounted intrinsic, expired, and non-positive prices must all
    # return None rather than a fabricated volatility.
    assert implied_vol(0.01, 100.0, 50.0, 1.0, "call", 0.05, 0.0) is None
    assert implied_vol(5.0, 100.0, 100.0, 0.0, "call", 0.05, 0.0) is None
    assert implied_vol(0.0, 100.0, 100.0, 1.0, "call", 0.05, 0.0) is None
    assert implied_vol(None, 100.0, 100.0, 1.0, "call") is None


def test_invalid_inputs_raise():
    with pytest.raises(ValueError):
        all_greeks(100.0, 100.0, 1.0, 0.2, "straddle")
    with pytest.raises(ValueError):
        all_greeks(100.0, 100.0, 0.0, 0.2, "call")
    with pytest.raises(ValueError):
        all_greeks(-1.0, 100.0, 1.0, 0.2, "call")


def test_net_greeks_signs_and_scaling():
    long_leg = all_greeks(100.0, 100.0, 0.5, 0.2, "call", 0.04, 0.0)
    short_leg = all_greeks(100.0, 110.0, 0.5, 0.2, "call", 0.04, 0.0)
    net = net_greeks([(long_leg, 1), (short_leg, -1)])
    assert net["delta"] == pytest.approx(
        long_leg["delta"] - short_leg["delta"])
    # A call vertical is long gamma at the lower strike and short at the
    # higher one, so net gamma is positive when the near strike dominates.
    assert net["gamma"] > 0
    assert "lam" not in net


# --------------------------------------------------- solver honesty tests

@pytest.mark.parametrize("spot,strike,t,sigma,kind", [
    (100.0, 60.0, 30 / 365, 0.05, "call"),
    (100.0, 60.0, 30 / 365, 0.20, "call"),
    (100.0, 50.0, 30 / 365, 0.20, "call"),
    (100.0, 180.0, 30 / 365, 0.20, "put"),
    (100.0, 150.0, 30 / 365, 0.20, "put"),
    (450.0, 405.0, 1 / 365, 0.35, "call"),
    (100.0, 95.0, 1 / 365, 0.20, "call"),
    (100.0, 105.0, 1 / 365, 0.20, "put"),
])
def test_implied_vol_refuses_prices_that_do_not_identify_a_volatility(
        spot, strike, t, sigma, kind):
    """A price dominated by intrinsic carries no volatility information.

    Every case here previously returned a number: usually the solver's own
    0.30 seed, sometimes a value one or two Newton steps past it. Four
    different true volatilities collapsed onto an identical answer. The
    only correct output is None, so the contract is skipped rather than
    published with a fabricated volatility and a full Greek ladder built
    on top of it.
    """
    price = bs_price(spot, strike, t, sigma, kind, 0.04, 0.0)
    assert implied_vol(price, spot, strike, t, kind, 0.04, 0.0) is None


def test_implied_vol_never_returns_the_seed_by_accident():
    # The seed is 0.30. If a solve returns exactly 0.30, it must be because
    # the true volatility is 0.30, which this asserts by repricing.
    for strike in (60.0, 80.0, 100.0, 120.0, 160.0):
        for t in (1 / 365, 7 / 365, 30 / 365, 180 / 365):
            for kind in ("call", "put"):
                for true_sigma in (0.05, 0.12, 0.30, 0.85):
                    price = bs_price(100.0, strike, t, true_sigma, kind,
                                     0.04, 0.0)
                    got = implied_vol(price, 100.0, strike, t, kind, 0.04,
                                      0.0)
                    if got is None:
                        continue
                    assert abs(got - true_sigma) < 1e-3, (
                        "K={} t={:.5f} {}: true {} returned {}".format(
                            strike, t, kind, true_sigma, got))


def test_greek_roster_is_exactly_the_documented_sixteen():
    # Asserting against GREEK_KEYS alone is self-referential: the roster
    # and the ladder come from the same module, so dropping one from both
    # passes. This pins the names independently.
    expected = {"delta", "gamma", "vega", "theta", "rho", "lam", "vanna",
                "vomma", "charm", "veta", "speed", "zomma", "color",
                "ultima", "dual_delta", "dual_gamma"}
    assert set(GREEK_KEYS) == expected
    assert set(all_greeks(100.0, 100.0, 0.5, 0.2, "call")) == \
        expected | {"price"}


def test_net_greeks_reports_missing_legs_rather_than_zeroing_them():
    full = all_greeks(100.0, 100.0, 0.5, 0.2, "call", 0.04, 0.0)
    partial = dict(full)
    partial["delta"] = None
    net = net_greeks([(full, 1), (partial, 1)])
    assert net["complete"] is False
    assert net["missing"]["delta"] == 1
    # The surviving total is the one leg that had a delta, and the caller
    # can see that it is half a position rather than a small one.
    assert net["delta"] == pytest.approx(full["delta"])
    assert net_greeks([(full, 1)])["complete"] is True


@pytest.mark.parametrize("kwargs,fragment", [
    ({"sigma": 20.0}, "per 1.00"),
    ({"t": 30.0 * 365}, "in years"),
])
def test_unit_errors_are_refused_not_priced(kwargs, fragment):
    # Volatility as a percentage and time in days both produce a complete,
    # finite, entirely wrong ladder if allowed through.
    args = {"spot": 100.0, "strike": 100.0, "t": 1.0, "sigma": 0.2,
            "kind": "call"}
    args.update(kwargs)
    with pytest.raises(ValueError) as excinfo:
        all_greeks(**args)
    assert fragment in str(excinfo.value)


def test_price_never_goes_negative_from_cancellation():
    # Deep out of the money the two discounted terms nearly cancel and the
    # difference underflows to a small negative number.
    price = bs_price(100.0, 160.0, 30 / 365, 0.20, "call", 0.04, 0.0)
    assert price >= 0.0
