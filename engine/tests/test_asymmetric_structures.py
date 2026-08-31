"""Ratio spreads, broken wing butterflies and jade lizards.

WHAT WOULD BREAK. These three structures are asymmetric on purpose, and
each carries one claim that is easy to state and easy to get wrong:

  ratio_spread            the short side is uncapped. If the extra short
                          were ever dropped, or its quantity silently
                          became one, the loss would come back as a
                          comfortable number instead of infinity and the
                          structure would look defined-risk.
  broken_wing_butterfly   the wings are unequal and the credit is what
                          makes one side free. Equal wings, or a debit,
                          and there is risk on both sides while the
                          registry still calls it a credit.
  jade_lizard             there is no upside risk only when the credit
                          reaches the width of the call spread. That is a
                          property of the strikes and the premiums that
                          were actually available, not of the shape, so it
                          is measured and reported rather than assumed.

The payoffs here are hand computed from round premiums at several
settlement prices, so the expected numbers do not come from the builders
and a builder that agrees with itself cannot pass. The builder tests then
check that the legs it selects satisfy the definition, on a chain listed
finely enough to carry the structures.

Copyright (C) 2026 Iman Samizadeh. Licensed under the PolyForm Noncommercial License 1.0.0.
"""

import pytest

from optiondesk_engine.pricing.black_scholes import bs_price
from optiondesk_engine.strategies.outlook import Outlook
from optiondesk_engine.strategies.payoff import (
    INF,
    Leg,
    analyze,
    net_option_cash,
    pnl_at_expiry,
)
from optiondesk_engine.strategies.playbook import (
    PLAYBOOK,
    build,
    describe,
    recommend,
    split_chain,
)

REL = 1e-9


def _chain(spot=700.0, lo=600.0, hi=800.0, step=1.0, days=20.0, iv=0.20,
           rate=0.04, spread=0.02):
    """Synthetic snapshot priced with the engine's own model.

    Priced from Black-Scholes for the reason the older fixture gives: a
    chain that is not arbitrage-free produces structures that cannot exist.

    The default is listed finely, one point apart on a seven hundred point
    underlying, because that is what an index chain looks like and it is
    what these three structures need. A five point grid on a hundred point
    underlying cannot finance a credit ratio spread near the money at all:
    two calls one strike out are worth less than the one at the money, and
    the builder correctly refuses. That is a fact about the chain rather
    than a defect, and it is asserted below.
    """
    t = days / 365.0
    contracts = []
    strike = lo
    while strike <= hi + 1e-9:
        for kind in ("call", "put"):
            mid = bs_price(spot, float(strike), t, iv, kind, rate, 0.0)
            contracts.append({
                "symbol": "T{}{:g}".format(kind[0].upper(), strike),
                "type": kind,
                "strike": float(strike),
                "bid": max(mid - spread, 0.0),
                "ask": mid + spread,
                "mid": mid,
                "iv": iv,
                "open_interest": 500,
                "volume": 100,
            })
        strike += step
    return {"underlying": "TEST", "spot": spot, "expiry": "2026-09-18",
            "days_to_expiry": days, "contracts": contracts}


def _coarse_chain():
    """The five point grid the rest of the engine suite uses."""
    return _chain(spot=100.0, lo=80.0, hi=120.0, step=5.0, days=30.0,
                  iv=0.25, spread=0.10)


def _at(legs, prices):
    return [pnl_at_expiry(legs, price) for price in prices]


# ------------------------------------------------------- hand computations

# Buy one 100 call at 6.00, sell two 110 calls at 3.50 each. Cash in is
# 7.00 against 6.00 out, so the trade opens for a 1.00 credit, and above
# 110 the second short is naked and the position loses a point per point.
RATIO_LEGS = [Leg("call", +1, 6.0, strike=100.0),
              Leg("call", -1, 3.5, strike=110.0, qty=2.0)]

RATIO_POINTS = [
    (80.0, 1.0),      # everything worthless, the credit is kept
    (100.0, 1.0),     # at the long strike, still just the credit
    (105.0, 6.0),     # 5 of intrinsic on the long, shorts worthless
    (110.0, 11.0),    # the peak: credit plus the distance between strikes
    (115.0, 6.0),     # 15 long against 2 x 5 short
    (130.0, -9.0),    # 30 long against 2 x 20 short
    (200.0, -79.0),   # and it keeps going
]


@pytest.mark.parametrize("price,expected", RATIO_POINTS)
def test_ratio_spread_payoff_matches_hand_computation(price, expected):
    assert pnl_at_expiry(RATIO_LEGS, price) == pytest.approx(expected,
                                                             rel=REL)


def test_ratio_spread_metrics_match_hand_computation():
    metrics = analyze(RATIO_LEGS, spot=100.0)
    assert net_option_cash(RATIO_LEGS) == pytest.approx(1.0, rel=REL)
    assert metrics["trade_type"] == "credit"
    assert metrics["max_gain"] == pytest.approx(11.0, rel=REL)
    # 110 plus the peak: past there each point costs one.
    assert metrics["breakevens"] == pytest.approx([121.0], rel=REL)
    # A credit means the downside never crosses zero, so there is one
    # breakeven and not two.
    assert len(metrics["breakevens"]) == 1


def test_the_ratio_spread_short_side_is_unlimited_rather_than_a_number():
    """The uncapped side is the point of the structure.

    If it were ever reported as a number, a naked short would be presented
    as defined risk and the comparison would rank it on a denominator it
    does not have.
    """
    metrics = analyze(RATIO_LEGS, spot=100.0)
    assert metrics["max_loss"] == -INF
    assert metrics["reward_risk"] is None
    assert metrics["risk_free"] is False
    # Not merely large: it is still falling, one point per point.
    far, further = _at(RATIO_LEGS, [1000.0, 2000.0])
    assert further - far == pytest.approx(-1000.0, rel=REL)


# Buy one 100 call at 8.00, sell two 110 calls at 4.60, buy one 125 call at
# 0.60. The near wing is 10 wide and the far wing 15, and the far leg is
# cheap enough that the whole thing opens for a 0.60 credit.
BWB_LEGS = [Leg("call", +1, 8.0, strike=100.0),
            Leg("call", -1, 4.6, strike=110.0, qty=2.0),
            Leg("call", +1, 0.6, strike=125.0)]

BWB_POINTS = [
    (0.01, 0.6),      # nothing below the lower strike can lose
    (90.0, 0.6),
    (100.0, 0.6),
    (110.0, 10.6),    # the peak: credit plus the near wing
    (115.0, 5.6),
    (125.0, -4.4),    # credit plus near wing less far wing
    (140.0, -4.4),    # flat once the far wing is in the money
    (500.0, -4.4),
]


@pytest.mark.parametrize("price,expected", BWB_POINTS)
def test_broken_wing_butterfly_payoff_matches_hand_computation(price,
                                                               expected):
    assert pnl_at_expiry(BWB_LEGS, price) == pytest.approx(expected, rel=REL)


def test_broken_wing_butterfly_metrics_match_hand_computation():
    metrics = analyze(BWB_LEGS, spot=100.0)
    assert net_option_cash(BWB_LEGS) == pytest.approx(0.6, rel=REL)
    assert metrics["trade_type"] == "credit"
    assert metrics["max_gain"] == pytest.approx(10.6, rel=REL)
    assert metrics["max_loss"] == pytest.approx(-4.4, rel=REL)
    assert metrics["breakevens"] == pytest.approx([120.6], rel=REL)
    assert metrics["reward_risk"] == pytest.approx(10.6 / 4.4, rel=REL)


def test_the_broken_wing_carries_no_risk_on_the_credit_side():
    """One side free is the whole reason to widen a wing.

    It holds because the trade opened for a credit, not because the wings
    are unequal. Equal wings paid for with a debit lose that debit here,
    which is what the same structure does when it is not a credit.
    """
    below = _at(BWB_LEGS, [0.01, 50.0, 99.9])
    assert all(value > 0 for value in below)
    assert below == pytest.approx([0.6, 0.6, 0.6], rel=REL)
    # And the wider wing is where that is paid for: the loss above the top
    # strike is exactly the wing difference less the credit.
    assert pnl_at_expiry(BWB_LEGS, 300.0) == pytest.approx(
        0.6 + 10.0 - 15.0, rel=REL)


# Sell the 90 put at 2.00 and the 110 call at 3.00, buy the 114 call at
# 0.50. The credit is 4.50 against a call spread 4.00 wide, so the rally
# side is covered with half a point to spare.
JADE_COVERED = [Leg("put", -1, 2.0, strike=90.0),
                Leg("call", -1, 3.0, strike=110.0),
                Leg("call", +1, 0.5, strike=114.0)]

# The same trade with the long call one strike further out: the width is
# now 5.00, the credit is unchanged, and the rally side is not covered.
JADE_UNCOVERED = [Leg("put", -1, 2.0, strike=90.0),
                  Leg("call", -1, 3.0, strike=110.0),
                  Leg("call", +1, 0.5, strike=115.0)]

JADE_POINTS = [
    (0.0, -85.5),     # the short put, bounded only by zero
    (80.0, -5.5),
    (90.0, 4.5),      # the credit, kept in full
    (100.0, 4.5),
    (110.0, 4.5),
    (112.0, 2.5),
    (114.0, 0.5),     # credit less the width of the call spread
    (500.0, 0.5),     # and flat above the long call
]


@pytest.mark.parametrize("price,expected", JADE_POINTS)
def test_jade_lizard_payoff_matches_hand_computation(price, expected):
    assert pnl_at_expiry(JADE_COVERED, price) == pytest.approx(expected,
                                                               rel=REL)


def test_jade_lizard_metrics_match_hand_computation():
    metrics = analyze(JADE_COVERED, spot=100.0)
    assert net_option_cash(JADE_COVERED) == pytest.approx(4.5, rel=REL)
    assert metrics["trade_type"] == "credit"
    assert metrics["max_gain"] == pytest.approx(4.5, rel=REL)
    # The short put is the whole risk, and the bound is the underlying
    # reaching zero rather than infinity.
    assert metrics["max_loss"] == pytest.approx(-85.5, rel=REL)
    # Only the downside crosses zero when the rally side is covered.
    assert metrics["breakevens"] == pytest.approx([85.5], rel=REL)


def test_the_covered_jade_lizard_cannot_lose_on_a_rally():
    """Credit 4.50 against a 4.00 wide call spread leaves 0.50 above."""
    above = _at(JADE_COVERED, [114.0, 200.0, 5000.0])
    assert above == pytest.approx([0.5, 0.5, 0.5], rel=REL)
    assert all(value > 0 for value in above)


def test_the_uncovered_jade_lizard_does_lose_on_a_rally():
    """Same credit, a 5.00 wide spread, and the property is gone.

    This is the case the field exists for. The two structures differ by one
    strike and nothing about their shape distinguishes them, so a claim
    made from the shape alone is right half the time.
    """
    above = _at(JADE_UNCOVERED, [115.0, 200.0, 5000.0])
    assert above == pytest.approx([-0.5, -0.5, -0.5], rel=REL)
    metrics = analyze(JADE_UNCOVERED, spot=100.0)
    assert metrics["breakevens"] == pytest.approx([85.5, 114.5], rel=REL)


# --------------------------------------------------------------- builders

def test_the_ratio_spread_builder_sells_more_than_it_buys_for_a_credit():
    plan = build("ratio_spread", split_chain(_chain()))
    assert plan is not None
    long_leg, short_leg = plan["legs"]
    assert long_leg.kind == short_leg.kind == "call"
    assert long_leg.side == +1 and short_leg.side == -1
    assert short_leg.qty == pytest.approx(2.0 * long_leg.qty, rel=REL)
    assert short_leg.strike > long_leg.strike
    metrics = plan["analysis"]
    assert metrics["net_cash"] > 0
    assert metrics["max_loss"] == -INF
    # The peak sits at the short strike and is the credit plus the distance
    # between the strikes, which is the identity that says the legs are
    # wired the way the structure is defined.
    assert metrics["max_gain"] == pytest.approx(
        metrics["net_cash"] + (short_leg.strike - long_leg.strike), rel=REL)
    assert metrics["breakevens"] == pytest.approx(
        [short_leg.strike + metrics["max_gain"]], rel=REL)


def test_the_ratio_spread_builder_takes_the_furthest_financed_strike():
    """Further out is strictly safer, so the credit is what binds.

    Picking the nearest financed strike instead would hand back a lower
    breakeven and a smaller tent for no compensation.
    """
    chain = split_chain(_chain())
    plan = build("ratio_spread", chain)
    chosen = plan["legs"][1].strike
    beyond = [option for option in chain["calls"]
              if float(option["strike"]) > chosen]
    assert beyond, "the chain must list strikes past the one chosen"
    for option in beyond:
        legs = [plan["legs"][0],
                Leg("call", -1, float(option["mid"]),
                    strike=float(option["strike"]), qty=2.0)]
        assert analyze(legs, spot=chain["spot"])["net_cash"] <= 0, (
            "strike {} also pays a credit and is further out".format(
                option["strike"]))


def test_the_ratio_spread_refuses_rather_than_returning_a_debit():
    """On a five point grid two calls one strike out cost less than one at
    the money, so no near-the-money 1x2 can be a credit. The registry
    declares this structure a credit, so a debit build would be labelled
    by the table as something the arithmetic says it is not.
    """
    assert build("ratio_spread", split_chain(_coarse_chain())) is None


def test_a_ratio_of_one_is_refused_because_it_is_a_vertical():
    with pytest.raises(ValueError):
        build("ratio_spread", split_chain(_chain()), ratio=1.0)


def test_the_broken_wing_builder_widens_only_the_far_wing():
    plan = build("broken_wing_butterfly", split_chain(_chain()))
    assert plan is not None
    lower, body, upper = plan["legs"]
    assert [leg.kind for leg in plan["legs"]] == ["call"] * 3
    assert [leg.side for leg in plan["legs"]] == [+1, -1, +1]
    assert body.qty == pytest.approx(2.0 * lower.qty, rel=REL)
    near = body.strike - lower.strike
    far = upper.strike - body.strike
    assert near > 0
    assert far > near, "the far wing must be the wider one"
    metrics = plan["analysis"]
    assert metrics["net_cash"] > 0
    assert metrics["max_gain"] == pytest.approx(metrics["net_cash"] + near,
                                                rel=REL)
    assert metrics["max_loss"] == pytest.approx(
        metrics["net_cash"] + near - far, rel=REL)
    assert pnl_at_expiry(plan["legs"], 0.01) == pytest.approx(
        metrics["net_cash"], rel=REL)


def test_the_broken_wing_builder_takes_the_nearest_far_wing_that_pays():
    """Walking further out buys more credit and more risk than needed.

    Measured on this chain: the far wing pays nothing until 1.75 times the
    near wing, and every strike past that pays more. Taking the first one
    is what keeps the extra risk to the least the chain will finance.
    """
    chain = split_chain(_chain())
    plan = build("broken_wing_butterfly", chain, far_wing_multiple=1.5)
    lower, body, upper = plan["legs"]
    near = body.strike - lower.strike
    far = upper.strike - body.strike
    assert far / near == pytest.approx(1.75, rel=1e-6)
    for option in chain["calls"]:
        strike = float(option["strike"])
        if not body.strike + near * 1.5 <= strike < upper.strike:
            continue
        legs = [lower, body,
                Leg("call", +1, float(option["mid"]), strike=strike)]
        assert analyze(legs, spot=chain["spot"])["net_cash"] <= 0, (
            "a nearer far wing at {} also pays a credit".format(strike))


def test_the_broken_wing_builder_refuses_a_far_wing_past_the_cap():
    """Past the cap the far leg is a disaster hedge, not a wing.

    With the search confined to between 1.5 and 1.6 times the near wing,
    nothing in the window pays a credit on this chain and the builder has
    to refuse rather than reach further out for one.
    """
    assert build("broken_wing_butterfly", split_chain(_chain()),
                 far_wing_multiple=1.5, max_far_wing_multiple=1.6) is None


def test_the_broken_wing_refuses_rather_than_returning_a_debit():
    assert build("broken_wing_butterfly",
                 split_chain(_coarse_chain())) is None


def test_equal_wings_are_refused_because_that_is_a_butterfly():
    with pytest.raises(ValueError):
        build("broken_wing_butterfly", split_chain(_chain()),
              far_wing_multiple=1.0)


def test_the_jade_lizard_measures_the_condition_it_reports():
    """The field must follow the legs, not the name of the structure."""
    chain = split_chain(_chain())
    plan = build("jade_lizard", chain)
    assert plan is not None
    short_put, short_call, long_call = plan["legs"]
    assert (short_put.kind, short_put.side) == ("put", -1)
    assert (short_call.kind, short_call.side) == ("call", -1)
    assert (long_call.kind, long_call.side) == ("call", +1)
    assert short_put.strike < chain["spot"] < short_call.strike
    assert long_call.strike > short_call.strike

    metrics = plan["analysis"]
    width = long_call.strike - short_call.strike
    covered = metrics["net_cash"] >= width
    assert metrics["no_upside_risk"] is covered
    # And the flag agrees with the payoff, which is where it came from.
    above = pnl_at_expiry(plan["legs"], long_call.strike + 1.0)
    assert metrics["no_upside_risk"] is bool(above >= 0)
    assert above == pytest.approx(metrics["net_cash"] - width, rel=REL)


def test_the_jade_lizard_keeps_the_property_on_a_chain_that_allows_it():
    chain = split_chain(_chain())
    plan = build("jade_lizard", chain)
    assert plan["analysis"]["no_upside_risk"] is True
    assert plan["analysis"]["max_gain"] == pytest.approx(
        plan["analysis"]["net_cash"], rel=REL)
    # No upside risk means the only breakeven is the one below the put.
    assert len(plan["analysis"]["breakevens"]) == 1


def test_the_jade_lizard_takes_the_furthest_long_call_that_stays_covered():
    """The furthest covered strike is the largest credit that keeps the
    property, and the credit is the maximum gain. The next strike out has
    to break the condition, or a better structure was available and was
    not taken.
    """
    chain = split_chain(_chain())
    plan = build("jade_lizard", chain)
    short_put, short_call, long_call = plan["legs"]
    beyond = [option for option in chain["calls"]
              if float(option["strike"]) > long_call.strike]
    assert beyond, "the chain must list strikes past the one chosen"
    for option in beyond:
        legs = [short_put, short_call,
                Leg("call", +1, float(option["mid"]),
                    strike=float(option["strike"]))]
        assert pnl_at_expiry(legs, float(option["strike"]) + 1.0) < 0, (
            "a further long call at {} also stays covered".format(
                option["strike"]))


def test_the_jade_lizard_reports_false_when_the_credit_misses_the_width():
    """A five point grid on a hundred point underlying does not pay enough
    at the band edges to cover the narrowest call spread available. The
    structure is still built, because it is still a jade lizard, and the
    field says the property it is known for does not hold here.
    """
    chain = split_chain(_coarse_chain())
    plan = build("jade_lizard", chain)
    assert plan is not None
    metrics = plan["analysis"]
    assert metrics["no_upside_risk"] is False
    short_put, short_call, long_call = plan["legs"]
    assert metrics["net_cash"] < long_call.strike - short_call.strike
    assert pnl_at_expiry(plan["legs"], long_call.strike + 1.0) < 0
    # It shows up as a second breakeven on the way up.
    assert len(metrics["breakevens"]) == 2


def test_only_the_structure_that_measures_it_carries_the_field():
    """A flag on every plan would be read as a claim about every plan."""
    chain = split_chain(_chain())
    assert "no_upside_risk" in build("jade_lizard", chain)["analysis"]
    for name in ("ratio_spread", "broken_wing_butterfly", "iron_condor"):
        assert "no_upside_risk" not in build(name, chain)["analysis"]


def test_describe_renders_the_measured_condition_and_the_unbounded_side():
    chain = split_chain(_chain())
    assert "no upside risk: yes" in describe(build("jade_lizard", chain))
    assert "max loss: unlimited" in describe(build("ratio_spread", chain))
    assert "no upside risk" not in describe(build("ratio_spread", chain))


# --------------------------------------------------------------- registry

NEW = ("ratio_spread", "broken_wing_butterfly", "jade_lizard")


@pytest.mark.parametrize("name", NEW)
def test_the_new_structures_are_declared_the_way_they_build(name):
    """The registry's label has to match the arithmetic of the legs.

    The wider suite checks this on the five point chain, where two of the
    three correctly refuse to build. It is checked here on a chain that
    can carry them, which is where a mislabelled trade type would show.
    """
    plan = build(name, split_chain(_chain()))
    assert plan is not None
    assert plan["strategy"] == name
    assert plan["analysis"]["trade_type"] == plan["trade_type"]
    assert plan["analysis"]["max_gain"] > 0
    assert describe(plan).startswith(name)


@pytest.mark.parametrize("name", NEW)
def test_the_new_entries_carry_a_view_and_a_volatility_stance(name):
    meta = PLAYBOOK[name]
    assert meta["build"] is not None
    assert meta["needs_underlying"] is False
    assert meta["trade_type"] == "credit"
    assert meta["vol_view"] in ("crush", "expand", "any")
    assert meta["outlooks"]
    assert all(isinstance(outlook, Outlook) for outlook in meta["outlooks"])
    assert len(meta["when_to_use"]) > 40


def test_recommend_offers_the_new_structures_for_the_views_they_declare():
    """They are registry entries, so ranking must find them without any of
    them being named in the ranking code.
    """
    for name in NEW:
        for outlook in PLAYBOOK[name]["outlooks"]:
            ranked = [entry for entry, _, _ in
                      recommend(outlook, vol_view="crush")]
            assert name in ranked, "{} missing for {}".format(name, outlook)
    # A strong rally is the direction the ratio spread loses without limit
    # in, so it must never lead for that view. The existing heuristic still
    # lists it, on the same adjacency rule that lists the iron condor and
    # the cash secured put there, but a structure that declared the strong
    # direction it cannot survive would come out on top.
    strong_bull = [entry for entry, _, _ in
                   recommend(Outlook.STRONG_BULLISH, vol_view="crush")]
    assert strong_bull[0] != "ratio_spread"
    assert strong_bull[0] == "long_call"
