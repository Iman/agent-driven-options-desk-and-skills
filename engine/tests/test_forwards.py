"""Options on futures and on foreign exchange.

WHAT WOULD BREAK. Both models are written as substitutions into the equity
formula, which is correct and is also exactly the kind of shortcut that is
wrong in a way nobody notices: swap the wrong argument and the price is
still plausible, still positive, still monotone in volatility. So none of
these tests compare the module against itself. Each closed form is written
out here independently, from the published formula, and the module has to
match it.

The put-call parity checks matter for the same reason. Parity holds for a
correct model and fails for most incorrect ones, and it does not care how
the price was computed.
"""

import math

import pytest

from optiondesk_engine.pricing.black_scholes import bs_price
from optiondesk_engine.pricing.forwards import (
    black76_greeks,
    black76_implied_vol,
    black76_price,
    forward_from_spot,
    garman_kohlhagen_greeks,
    garman_kohlhagen_implied_vol,
    garman_kohlhagen_price,
)


def _cdf(x):
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def _black76_reference(future, strike, t, sigma, kind, r):
    """Black 1976, written from the published formula, not from the module."""
    root = sigma * math.sqrt(t)
    d1 = (math.log(future / strike) + 0.5 * sigma * sigma * t) / root
    d2 = d1 - root
    discount = math.exp(-r * t)
    if kind == "call":
        return discount * (future * _cdf(d1) - strike * _cdf(d2))
    return discount * (strike * _cdf(-d2) - future * _cdf(-d1))


def _gk_reference(spot, strike, t, sigma, kind, rd, rf):
    """Garman and Kohlhagen 1983, written out independently."""
    root = sigma * math.sqrt(t)
    d1 = (math.log(spot / strike) + (rd - rf + 0.5 * sigma * sigma) * t) / root
    d2 = d1 - root
    if kind == "call":
        return (spot * math.exp(-rf * t) * _cdf(d1)
                - strike * math.exp(-rd * t) * _cdf(d2))
    return (strike * math.exp(-rd * t) * _cdf(-d2)
            - spot * math.exp(-rf * t) * _cdf(-d1))


CASES = [
    (100.0, 100.0, 0.50, 0.25, 0.04),
    (100.0, 80.0, 1.00, 0.35, 0.02),
    (100.0, 130.0, 0.25, 0.60, 0.05),
    (55.0, 50.0, 2.00, 0.20, 0.03),
    (3200.0, 3300.0, 0.08, 0.18, 0.045),
]


@pytest.mark.parametrize("future,strike,t,sigma,r", CASES)
@pytest.mark.parametrize("kind", ["call", "put"])
def test_black76_matches_the_published_formula(future, strike, t, sigma, r,
                                               kind):
    expected = _black76_reference(future, strike, t, sigma, kind, r)
    got = black76_price(future, strike, t, sigma, kind, r)
    assert got == pytest.approx(expected, rel=1e-12), (
        "{} {} differs from the reference".format(kind, strike))


@pytest.mark.parametrize("future,strike,t,sigma,r", CASES)
def test_black76_obeys_put_call_parity(future, strike, t, sigma, r):
    """c - p = e^-rT (F - K). Fails for almost any wrong substitution."""
    call = black76_price(future, strike, t, sigma, "call", r)
    put = black76_price(future, strike, t, sigma, "put", r)
    assert call - put == pytest.approx(
        math.exp(-r * t) * (future - strike), abs=1e-9)


def test_black76_is_not_just_the_equity_price():
    """The substitution has to actually change something.

    An equity call on a spot of 100 and a futures call on a future of 100
    are different numbers whenever the rate is not zero. A test that passes
    for both would not detect the carry term being dropped.
    """
    equity = bs_price(100.0, 100.0, 1.0, 0.25, "call", 0.05, 0.0)
    future = black76_price(100.0, 100.0, 1.0, 0.25, "call", 0.05)
    assert future < equity
    assert abs(future - equity) > 0.5


@pytest.mark.parametrize("spot,strike,t,sigma,rd,rf", [
    (1.10, 1.10, 0.50, 0.10, 0.04, 0.02),
    (1.35, 1.20, 1.00, 0.14, 0.05, 0.01),
    (0.85, 0.95, 0.25, 0.09, 0.02, 0.04),
    (150.0, 145.0, 2.00, 0.11, 0.005, 0.045),
])
@pytest.mark.parametrize("kind", ["call", "put"])
def test_garman_kohlhagen_matches_the_published_formula(spot, strike, t,
                                                        sigma, rd, rf, kind):
    expected = _gk_reference(spot, strike, t, sigma, kind, rd, rf)
    got = garman_kohlhagen_price(spot, strike, t, sigma, kind, rd, rf)
    assert got == pytest.approx(expected, rel=1e-12)


def test_garman_kohlhagen_obeys_put_call_parity():
    """c - p = S e^-rfT - K e^-rdT."""
    spot, strike, t, sigma, rd, rf = 1.10, 1.05, 0.75, 0.12, 0.04, 0.015
    call = garman_kohlhagen_price(spot, strike, t, sigma, "call", rd, rf)
    put = garman_kohlhagen_price(spot, strike, t, sigma, "put", rd, rf)
    assert call - put == pytest.approx(
        spot * math.exp(-rf * t) - strike * math.exp(-rd * t), abs=1e-12)


def test_the_two_rates_are_not_interchangeable():
    """Swapping the domestic and foreign rate is the obvious wrong wiring.

    It has to produce a different price, or nothing detects the arguments
    being crossed.
    """
    a = garman_kohlhagen_price(1.10, 1.10, 1.0, 0.12, "call", 0.05, 0.01)
    b = garman_kohlhagen_price(1.10, 1.10, 1.0, 0.12, "call", 0.01, 0.05)
    assert abs(a - b) > 0.01, (a, b)


def test_a_futures_option_on_the_forward_equals_the_currency_option():
    """The two models agree when they are given the same economics.

    A currency option priced on spot with two rates is the same contract as
    a futures option on the forward implied by those rates, discounted at
    the domestic rate. If the substitutions are right this identity holds
    to machine precision; if either is wrong it does not hold at all.
    """
    spot, strike, t, sigma, rd, rf = 1.10, 1.15, 1.5, 0.13, 0.045, 0.012
    forward = forward_from_spot(spot, t, rd, rf)
    for kind in ("call", "put"):
        gk = garman_kohlhagen_price(spot, strike, t, sigma, kind, rd, rf)
        b76 = black76_price(forward, strike, t, sigma, kind, rd)
        assert gk == pytest.approx(b76, rel=1e-12), kind


def test_the_greeks_say_what_they_are_derivatives_of():
    """Futures delta is not equity delta, and saying so is not decoration.

    Hedging a futures delta means trading the future. A ladder that does
    not say which quantity it differentiated against invites the reader to
    hedge in the wrong instrument.
    """
    b76 = black76_greeks(100.0, 100.0, 0.5, 0.25, "call")
    assert b76["underlying_is"] == "futures_price"
    gk = garman_kohlhagen_greeks(1.10, 1.10, 0.5, 0.10, "call", 0.04, 0.02)
    assert gk["underlying_is"] == "fx_spot"
    assert set(b76) >= {"delta", "gamma", "vega", "theta", "vanna", "charm"}


def test_implied_volatility_round_trips_through_both_models():
    for price_fn, iv_fn, args in (
            (black76_price, black76_implied_vol, (100.0, 105.0, 0.75, 0.04)),
            (garman_kohlhagen_price, garman_kohlhagen_implied_vol,
             (1.10, 1.12, 0.5, 0.04, 0.015))):
        underlying, strike, t = args[0], args[1], args[2]
        rates = args[3:]
        for sigma in (0.08, 0.25, 0.60):
            price = price_fn(underlying, strike, t, sigma, "call", *rates)
            solved = iv_fn(price, underlying, strike, t, "call", *rates)
            assert solved == pytest.approx(sigma, rel=1e-6), (sigma, solved)


def test_a_price_that_identifies_no_volatility_is_refused():
    """The same refusal the equity solver makes, inherited not reimplemented."""
    deep = black76_price(100.0, 10.0, 0.01, 0.20, "call")
    assert black76_implied_vol(deep, 100.0, 10.0, 0.01, "call") is None


def test_the_forward_helper_is_not_a_no_op():
    """Passing a spot where a forward belongs is wrong by the whole carry."""
    assert forward_from_spot(100.0, 1.0, 0.05, 0.0) == pytest.approx(
        100.0 * math.exp(0.05), rel=1e-12)
    assert forward_from_spot(100.0, 1.0, 0.05, 0.05) == pytest.approx(100.0)
    with pytest.raises(ValueError):
        forward_from_spot(100.0, -1.0)
