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


def test_a_calendar_builds_when_the_two_ladders_differ(chains):
    """Real expiries are not listed on the same strike ladder.

    SPY on 2026-08-31 quoted the October expiry one point apart and the
    December expiry five points apart. The builder picked the near strike
    closest to spot, 766, then the far strike closest to that, 765, saw
    they differed and returned nothing, reporting that the strikes or
    quotes did not admit a calendar. A shared strike sat one point from
    spot in both chains. It made calendars unbuildable on most real pairs
    and blamed the data.

    The near chain here lists every point and the far chain every five, the
    same shape that produced the failure.
    """
    near = _chain(21, 0.22, spot=100.6, expiry="2026-09-18",
                  low=90, high=111, step=1)
    far = _chain(56, 0.24, spot=100.6, expiry="2026-10-23",
                 low=90, high=111, step=5)

    # Spot sits where the two ladders disagree, which is the whole point:
    # the near chain's closest strike to spot is 101, the far chain does
    # not list 101, and its own closest is 100. Choosing from the near
    # chain first therefore finds no match, while a strike both chains
    # quote sits well within a point of spot.
    near_only = min((c["strike"] for c in near["calls"]),
                    key=lambda s: abs(s - 100.6))
    assert near_only == 101.0
    assert 101.0 not in [c["strike"] for c in far["calls"]]
    assert 100.0 in [c["strike"] for c in far["calls"]]

    plan = calendar_spread(near, far, kind="call")
    assert plan is not None, "a shared strike existed and was not used"
    strikes = {leg.strike for leg in plan["legs"]}
    assert len(strikes) == 1, "a calendar has one strike in both expiries"
    assert strikes.pop() == 100.0
    assert plan["near_days"] < plan["far_days"]


def test_a_calendar_still_refuses_when_no_strike_is_shared(chains):
    """Narrowing the failure must not remove it. Two ladders with nothing in
    common are a diagonal at best, and calling that a calendar would
    misdescribe its risk.
    """
    near = _chain(21, 0.22, spot=100.0, expiry="2026-09-18",
                  low=90, high=111, step=5)
    far = _chain(56, 0.24, spot=100.0, expiry="2026-10-23",
                 low=92, high=113, step=5)
    assert not ({c["strike"] for c in near["calls"]}
                & {c["strike"] for c in far["calls"]})
    assert calendar_spread(near, far, kind="call") is None


def _delta_chain(days, iv, spot=100.0, expiry="2026-01-01", low=70, high=131,
                 step=1):
    """A chain wide enough to hold a 65 delta leg and a 25 delta leg."""
    return _chain(days, iv, spot=spot, expiry=expiry, low=low, high=high,
                  step=step)


def test_a_ratio_diagonal_holds_more_long_delta_than_short(chains):
    """The constraint that makes it that structure rather than a 1x1 with
    an extra contract. Ported from the author's 001-qaunt work, where the
    ratio was the point: the front shorts subsidise the carry while the
    delta ratio stays below one, so the move is not capped.
    """
    near = _delta_chain(28, 0.22, expiry="2026-09-18")
    far = _delta_chain(112, 0.24, expiry="2026-12-18")

    for name, kind in (("ratio_call_diagonal", "call"),
                       ("ratio_put_diagonal", "put")):
        plan = build_time_spread(name, near, far)
        assert plan is not None, "{} did not build".format(name)
        assert plan["kind"] == kind
        assert 0 < plan["delta_ratio"] < 1, (
            "short delta mass must stay below long delta mass")
        longs = [leg for leg in plan["legs"] if leg.side > 0]
        shorts = [leg for leg in plan["legs"] if leg.side < 0]
        assert len(longs) == 1 and len(shorts) == 1
        assert longs[0].qty > shorts[0].qty, "more back month than front"
        assert longs[0].days > shorts[0].days, "the long is the back month"


def test_a_ratio_diagonal_refuses_a_net_short_shape(chains):
    """The check that carries the claim, and for a while did not exist.

    An audit built this structure through the public API at one long
    against two short. It satisfied the delta bound at a ratio of 0.76 and
    was a net short call whose loss is unbounded on the upside, measured at
    -3787 over a wide scan, while the docstring, the skill reference, the
    dashboard panel and the plan schema all said the delta bound was what
    kept the move uncapped. It never did. Holding more back-month
    contracts than front-month ones is what does.
    """
    from optiondesk_engine.strategies import timespread

    near = _delta_chain(28, 0.22, expiry="2026-09-18")
    far = _delta_chain(112, 0.24, expiry="2026-12-18")

    for long_qty, short_qty in ((1.0, 2.0), (1.0, 1.0), (2.0, 3.0)):
        assert timespread._ratio_diagonal(
            near, far, "call", long_qty=long_qty,
            short_qty=short_qty) is None, (
                "{} long against {} short is not a ratio diagonal".format(
                    long_qty, short_qty))

    assert timespread._ratio_diagonal(near, far, "call", long_qty=2.0,
                                      short_qty=1.0) is not None


def test_a_ratio_diagonal_refuses_a_short_that_is_not_further_out(chains):
    """The short leg has to sit beyond the long one in the trade's own
    direction, or the structure is not a diagonal at all.

    This check had no test until an audit deleted it and all 302 engine
    tests stayed green. Asking for a far out of the money long and a near
    the money short inverts the pair, which is the shape it exists to
    refuse.
    """
    from optiondesk_engine.strategies import timespread

    near = _delta_chain(28, 0.22, expiry="2026-09-18")
    far = _delta_chain(112, 0.24, expiry="2026-12-18")

    inverted = timespread._ratio_diagonal(near, far, "call", long_delta=0.10,
                                          short_delta=0.55, long_qty=2.0,
                                          short_qty=1.0)
    assert inverted is None

    ordered = timespread._ratio_diagonal(near, far, "call", long_delta=0.65,
                                         short_delta=0.25, long_qty=2.0,
                                         short_qty=1.0)
    assert ordered is not None
    strikes = {leg.side: leg.strike for leg in ordered["legs"]}
    assert strikes[-1] > strikes[1], "the short call must be the further one"


def test_a_ratio_diagonal_reads_its_own_tail(chains):
    """The third check reads the payoff rather than the contracts.

    Neither of the other two looks at the profit curve, so a leg mix whose
    far end falls away would pass both. This measures the slope at the edge
    of the scanned range in the structure's own direction and refuses a
    structure that gives ground there.
    """
    from optiondesk_engine.strategies import timespread

    near = _delta_chain(28, 0.22, expiry="2026-09-18")
    far = _delta_chain(112, 0.24, expiry="2026-12-18")
    plan = timespread._ratio_diagonal(near, far, "call")
    assert plan is not None

    spot = float(near["spot"])
    hi = spot * 1.40
    step = spot * 0.01
    from optiondesk_engine.strategies.timespread import pnl_at
    at_days = plan["near_days"]
    assert pnl_at(plan["legs"], hi, at_days) >= pnl_at(
        plan["legs"], hi - step, at_days), (
            "a structure that is refused when its tail turns down must not "
            "be returned with a tail that turns down")


def test_the_ratio_gives_back_less_than_the_one_by_one(chains):
    """The measurable difference between the two shapes, and the reason
    both are kept. A 1x1 diagonal hands profit back beyond the short
    strike as the long's time value drains against the short's intrinsic.
    """
    near = _delta_chain(28, 0.22, expiry="2026-09-18")
    far = _delta_chain(112, 0.24, expiry="2026-12-18")

    ratio = build_time_spread("ratio_call_diagonal", near, far)
    plain = build_time_spread("diagonal_spread", near, far, kind="call")
    assert ratio is not None and plain is not None

    # An absolute assertion, at two widths. The earlier version compared
    # two quantities that are both non-negative by construction, so
    # hardcoding the ratio's giveback to zero left it passing: it tested
    # the 1x1's formula and nothing about the ratio at all.
    from optiondesk_engine.strategies.timespread import analyze_at_front
    for span in (0.40, 2.0):
        wide = analyze_at_front(ratio["legs"], ratio["spot"], span=span)
        assert wide["upside_giveback"] == 0.0, (
            "the ratio hands back {} at span {}".format(
                wide["upside_giveback"], span))
    assert plain["analysis"]["upside_giveback"] > 0.0, (
        "the 1x1 is kept precisely because it does give profit back")


def test_the_snapshot_rates_choose_the_legs(chains):
    """Legs are selected at the chain's own carry, not at the defaults.

    An audit measured the difference on the live SPY pair: at the module
    defaults of 4 percent and no dividend the call short landed on 791 and
    the put long on 800; at the snapshot's own 3.735 percent and 0.9828
    percent dividend yield they landed on 790 and 795. Three of four legs
    moved. A delta target is a statement about carry, so reading the carry
    off the chain is not a refinement, it is the difference between
    selecting the contract the target names and a neighbouring one.
    """
    from optiondesk_engine.strategies import timespread

    near = _delta_chain(28, 0.22, expiry="2026-09-18")
    far = _delta_chain(112, 0.24, expiry="2026-12-18")

    defaults = timespread._ratio_diagonal(near, far, "call")

    # A dividend yield large enough to move the ladder, stated on the chain
    # the way a real snapshot states it.
    for chain in (near, far):
        chain["risk_free_rate"] = 0.01
        chain["dividend_yield"] = 0.08
    with_rates = timespread._ratio_diagonal(near, far, "call")

    assert defaults is not None and with_rates is not None
    assert (with_rates["risk_free_rate"], with_rates["dividend_yield"]) == (
        0.01, 0.08), "the plan must name the carry it used"
    assert defaults["risk_free_rate"] == timespread.DEFAULT_R

    picked = lambda plan: sorted(leg.strike for leg in plan["legs"])
    assert picked(defaults) != picked(with_rates), (
        "the carry did not reach the selection: same legs at 4 percent and "
        "no dividend as at 1 percent and 8 percent")


def test_a_maximum_on_the_scan_edge_says_so(chains):
    """A maximum that lands on the window boundary is a property of the
    window, not of the structure.

    An audit measured one published reward to risk of 4.90 that reads 1.47
    at a tenth of the scan width and 12.02 at two and a half times it, all
    of the same structure on the same chain, with the maximum sitting
    eleven standard deviations below spot at a tail probability around
    7e-29. The number was published as a bare ratio with nothing beside it
    saying where it came from.
    """
    from optiondesk_engine.strategies.timespread import analyze_at_front

    near = _delta_chain(28, 0.22, expiry="2026-09-18")
    far = _delta_chain(112, 0.24, expiry="2026-12-18")
    plan = build_time_spread("ratio_call_diagonal", near, far)
    assert plan is not None

    analysis = plan["analysis"]
    assert analysis["reward_risk_bounded_by_scan"] is True
    assert analysis["max_gain_on_boundary"] is True
    low_sd, high_sd = analysis["scan_range_sd"]
    assert low_sd < -2.0 and high_sd > 2.0
    assert "edge of that range" in analysis["note"]

    # And the ratio really does move with the window, which is the whole
    # reason the flag has to be there.
    narrow = analyze_at_front(plan["legs"], plan["spot"], span=0.10)
    wide = analyze_at_front(plan["legs"], plan["spot"], span=1.00)
    assert wide["max_gain"] > narrow["max_gain"] * 2


def test_an_interior_maximum_is_not_flagged(chains):
    """The flag has to distinguish. A structure whose peak sits inside the
    window carries a maximum that is its own.
    """
    from optiondesk_engine.strategies.timespread import analyze_at_front

    near, far = chains
    plan = calendar_spread(near, far, kind="call")
    assert plan is not None

    # A calendar's peak is where its strike is, which is inside any
    # sensible window, so the gain is its own number at every width.
    for span in (0.10, 0.40, 1.00):
        analysis = analyze_at_front(plan["legs"], plan["spot"], span=span)
        assert analysis["max_gain_on_boundary"] is False
        assert abs(analysis["max_gain"] - 1.3220) < 0.01

    # Widened to the price floor, the worst case is a real bound rather
    # than a window edge, and the flag has to stop firing there or it
    # would cry wolf on every structure.
    to_the_floor = analyze_at_front(plan["legs"], plan["spot"], span=1.00)
    assert to_the_floor["max_loss_on_boundary"] is False
    assert to_the_floor["reward_risk_bounded_by_scan"] is False

    # At a narrower window the same worst case IS the window, and says so.
    narrow = analyze_at_front(plan["legs"], plan["spot"], span=0.10)
    assert narrow["max_loss_on_boundary"] is True
