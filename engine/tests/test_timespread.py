"""Two-expiry structures.

Copyright (C) 2026 Iman Samizadeh. Licensed under the PolyForm Noncommercial License 1.0.0.

The properties tested here are the ones that distinguish a calendar from
every other structure: the surviving leg still has value at the near
expiry, the profit is a curve rather than line segments, and the whole
thing rests on a volatility assumption that has to be visible.
"""

import pytest

from optiondesk_engine.pricing.black_scholes import bs_price
from optiondesk_engine.strategies.timespread import (
    ASSUMPTION,
    TimeLeg,
    analyze_at_front,
    build_time_spread,
    calendar_spread,
    diagonal_spread,
    net_option_cash,
    payoff_curve,
    pnl_at,
)


def _chain(days, iv, spot=100.0, expiry="2026-01-01", low=85, high=116,
           step=5):
    contracts = {"calls": [], "puts": []}
    t = days / 365.0
    for strike in range(low, high, step):
        for kind in ("call", "put"):
            price = bs_price(spot, float(strike), t, iv, kind, 0.04, 0.0)
            contracts["calls" if kind == "call" else "puts"].append({
                "symbol": "{}{}{}".format(kind[0].upper(), strike, days),
                "type": kind, "strike": float(strike),
                "bid": max(price - 0.02, 0.0), "ask": price + 0.02,
                "mid": price, "iv": iv, "open_interest": 500, "volume": 50})
    contracts.update({"spot": spot, "days": float(days), "expiry": expiry})
    return contracts


@pytest.fixture
def chains():
    return _chain(21, 0.22, expiry="2026-09-18"), _chain(56, 0.24,
                                                         expiry="2026-10-23")


def test_a_leg_past_its_own_expiry_is_worth_intrinsic():
    leg = TimeLeg("call", -1, 2.0, 100.0, 1.0, 0.25, 21.0)
    assert leg.value_at(110.0, 21.0) == pytest.approx(10.0)
    assert leg.value_at(90.0, 21.0) == pytest.approx(0.0)
    # Past expiry, not merely at it.
    assert leg.value_at(110.0, 30.0) == pytest.approx(10.0)


def test_a_surviving_leg_still_has_time_value_at_the_near_expiry():
    """This is the whole mechanism. If the far leg were settled at the near
    expiry like every other structure, a calendar would be worth nothing
    and the payoff would be flat."""
    far = TimeLeg("call", +1, 4.0, 100.0, 1.0, 0.24, 56.0)
    value = far.value_at(100.0, 21.0)
    assert value > 0
    # It is worth less than at entry, having lost 21 days of time value,
    # but far more than the zero an expiry-settled model would give.
    assert value < far.value_at(100.0, 0.0)


def test_a_calendar_peaks_at_its_strike_and_loses_on_a_large_move(chains):
    near, far = chains
    plan = calendar_spread(near, far)
    legs = plan["legs"]
    at_days = plan["analysis"]["at_days"]

    at_strike = pnl_at(legs, 100.0, at_days)
    far_below = pnl_at(legs, 70.0, at_days)
    far_above = pnl_at(legs, 130.0, at_days)
    assert at_strike > 0
    assert far_below < 0 and far_above < 0
    assert at_strike > far_below and at_strike > far_above
    # Two breakevens, one either side of the peak.
    breakevens = plan["analysis"]["breakevens"]
    assert len(breakevens) == 2
    assert breakevens[0] < 100.0 < breakevens[1]


def test_a_calendar_is_a_debit_and_its_loss_is_bounded_by_it(chains):
    near, far = chains
    analysis = calendar_spread(near, far)["analysis"]
    assert analysis["trade_type"] == "debit"
    # The worst case is losing what was paid, which happens where the far
    # leg is worthless and the near one expired worthless too.
    assert analysis["max_loss"] == pytest.approx(analysis["net_cash"],
                                                 abs=1e-6)


def test_a_diagonal_leans_toward_its_short_strike(chains):
    near, far = chains
    plan = diagonal_spread(near, far, kind="call", offset=0.05)
    strikes = sorted(leg.strike for leg in plan["legs"])
    assert strikes[0] < strikes[1], "the short call must sit above the long"
    # The peak sits at the short strike rather than at spot.
    assert plan["analysis"]["max_gain_at"] > plan["spot"]


def test_a_put_diagonal_leans_the_other_way(chains):
    near, far = chains
    plan = diagonal_spread(near, far, kind="put", offset=0.05)
    short = [leg for leg in plan["legs"] if leg.side < 0][0]
    long_leg = [leg for leg in plan["legs"] if leg.side > 0][0]
    assert short.strike < long_leg.strike
    assert plan["analysis"]["max_gain_at"] < plan["spot"]


def test_the_chains_must_be_the_right_way_round(chains):
    near, far = chains
    with pytest.raises(ValueError) as excinfo:
        calendar_spread(far, near)
    assert "wrong way round" in str(excinfo.value)


def test_a_chain_without_a_shared_strike_is_not_a_calendar():
    """Silently returning a diagonal would misdescribe the risk."""
    near = _chain(21, 0.22, low=95, high=106, step=5)
    far = _chain(56, 0.24, low=70, high=81, step=5)
    assert calendar_spread(near, far) is None


def test_a_leg_with_no_volatility_is_refused():
    with pytest.raises(ValueError) as excinfo:
        TimeLeg("call", +1, 2.0, 100.0, 1.0, None, 30.0)
    assert "nothing to mark it with" in str(excinfo.value)


def test_contracts_without_a_usable_price_are_skipped():
    near = _chain(21, 0.22)
    for contract in near["calls"]:
        contract.update({"mid": None, "bid": None, "ask": None})
    far = _chain(56, 0.24)
    assert calendar_spread(near, far, kind="call") is None
    # The put side is untouched, so that one still builds.
    assert calendar_spread(near, far, kind="put") is not None


def test_the_volatility_assumption_travels_with_the_plan(chains):
    near, far = chains
    plan = calendar_spread(near, far)
    assert "bet on the difference between two volatilities" in \
        plan["assumption"]
    assert ASSUMPTION in plan["analysis"]["note"]
    assert "over the scanned range" in plan["analysis"]["note"]


def test_the_payoff_is_a_curve_not_line_segments(chains):
    near, far = chains
    plan = calendar_spread(near, far)
    prices, profits = payoff_curve(plan["legs"], 90.0, 110.0,
                                   plan["analysis"]["at_days"], points=41)
    # Second differences of a piecewise linear payoff are zero away from
    # the kinks. A calendar's are not.
    curvature = [profits[i + 1] - 2 * profits[i] + profits[i - 1]
                 for i in range(1, len(profits) - 1)]
    assert sum(1 for value in curvature if abs(value) > 1e-9) > 20


def test_net_cash_sign_convention_matches_the_rest_of_the_engine():
    legs = [TimeLeg("call", -1, 3.0, 100.0, 1.0, 0.2, 21.0),
            TimeLeg("call", +1, 5.0, 100.0, 1.0, 0.2, 56.0)]
    assert net_option_cash(legs) == pytest.approx(-2.0)


def test_build_by_name_and_its_error(chains):
    near, far = chains
    assert build_time_spread("calendar_spread", near, far) is not None
    with pytest.raises(KeyError):
        build_time_spread("not_a_spread", near, far)


def test_analysis_refuses_an_empty_position():
    with pytest.raises(ValueError):
        analyze_at_front([], 100.0)
