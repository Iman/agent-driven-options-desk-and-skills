"""Strategy payoff, playbook and friction.

The payoff cases are hand-computable, so the assertions are exact numbers
rather than properties. The closed-form probability and tail statistics are
cross-checked against a seeded Monte Carlo draw from the same distribution:
if the algebra is wrong, the two disagree.

Copyright (C) 2026 Iman Samizadeh. Licensed under AGPL-3.0-only.
"""

import math
import random

import pytest

from optiondesk_engine.pricing.black_scholes import bs_price
from optiondesk_engine.strategies.friction import plan_friction
from optiondesk_engine.strategies.outlook import (
    Outlook,
    classify_target,
    expected_move,
    one_sd_band,
)
from optiondesk_engine.strategies.payoff import (
    INF,
    Leg,
    analyze,
    net_option_cash,
    payoff_curve,
    pnl_at_expiry,
    probability_of_profit,
    tail_metrics,
)
from optiondesk_engine.strategies.playbook import (
    PLAYBOOK,
    build,
    describe,
    recommend,
    split_chain,
)


def _chain(spot=100.0, days=30.0, iv=0.25, spread=0.10):
    """Synthetic snapshot priced with the engine's own model.

    Priced from Black-Scholes rather than from a made-up formula, because a
    chain that is not arbitrage-free produces structures that cannot exist,
    and then a test failure says nothing about the code under test. An
    earlier version of this fixture priced options ad hoc and made a
    butterfly cost more than the distance between its strikes.
    """
    contracts = []
    t = days / 365.0
    for strike in range(80, 121, 5):
        for kind in ("call", "put"):
            mid = bs_price(spot, float(strike), t, iv, kind, 0.04, 0.0)
            contracts.append({
                "symbol": "T{}{}".format(kind[0].upper(), strike),
                "type": kind,
                "strike": float(strike),
                "bid": max(mid - spread, 0.0),
                "ask": mid + spread,
                "mid": mid,
                "iv": iv,
                "open_interest": 500,
                "volume": 100,
            })
    return {"underlying": "TEST", "spot": spot, "expiry": "2026-09-18",
            "days_to_expiry": days, "contracts": contracts}


# ------------------------------------------------------------------ payoff

def test_bull_call_spread_matches_hand_computation():
    # Buy the 90 call at 5.00, sell the 95 at 3.00. Net debit 2.00,
    # breakeven 92, maximum gain 3.00, maximum loss the debit.
    legs = [Leg("call", +1, 5.0, strike=90.0),
            Leg("call", -1, 3.0, strike=95.0)]
    metrics = analyze(legs, spot=90.0)
    assert metrics["net_cash"] == pytest.approx(-2.0)
    assert metrics["trade_type"] == "debit"
    assert metrics["breakevens"] == [92.0]
    assert metrics["max_gain"] == pytest.approx(3.0)
    assert metrics["max_loss"] == pytest.approx(-2.0)
    assert metrics["reward_risk"] == pytest.approx(1.5)


def test_long_call_gain_is_unbounded_and_loss_is_the_premium():
    legs = [Leg("call", +1, 4.0, strike=100.0)]
    metrics = analyze(legs, spot=100.0)
    assert metrics["max_gain"] == INF
    assert metrics["max_loss"] == pytest.approx(-4.0)
    assert metrics["breakevens"] == [104.0]
    assert metrics["reward_risk"] is None


def test_short_call_loss_is_unbounded():
    legs = [Leg("call", -1, 4.0, strike=100.0)]
    metrics = analyze(legs, spot=100.0)
    assert metrics["max_loss"] == -INF
    assert metrics["max_gain"] == pytest.approx(4.0)


def test_iron_condor_max_loss_is_width_minus_credit():
    legs = [Leg("put", -1, 2.0, strike=90.0),
            Leg("put", +1, 1.0, strike=85.0),
            Leg("call", -1, 2.0, strike=110.0),
            Leg("call", +1, 1.0, strike=115.0)]
    metrics = analyze(legs, spot=100.0)
    credit = 2.0
    assert metrics["net_cash"] == pytest.approx(credit)
    assert metrics["trade_type"] == "credit"
    assert metrics["max_gain"] == pytest.approx(credit)
    assert metrics["max_loss"] == pytest.approx(-(5.0 - credit))
    assert metrics["breakevens"] == [88.0, 112.0]


def test_covered_call_excludes_the_underlying_from_the_cash_label():
    # Buying stock costs money, but the option transaction is a credit,
    # and the label describes the option transaction.
    legs = [Leg("underlying", +1, 100.0), Leg("call", -1, 3.0, strike=105.0)]
    assert net_option_cash(legs) == pytest.approx(3.0)
    assert analyze(legs, spot=100.0)["trade_type"] == "credit"


def test_payoff_curve_includes_exact_strikes():
    legs = [Leg("call", +1, 5.0, strike=90.0),
            Leg("call", -1, 3.0, strike=95.0)]
    xs, ys = payoff_curve(legs, 80.0, 110.0, points=50)
    assert 90.0 in xs and 95.0 in xs
    assert len(xs) == len(ys)
    assert ys[0] == pytest.approx(-2.0)


def test_empty_legs_is_an_error_not_a_zero():
    with pytest.raises(ValueError):
        analyze([])


# ---------------------------------------------- distribution cross-checks

def _monte_carlo(legs, spot, iv, days, draws=200000, seed=7):
    """Independent draw from the same lognormal, for cross-checking."""
    rng = random.Random(seed)
    t = days / 365.0
    sd = iv * math.sqrt(t)
    mu = -0.5 * iv * iv * t
    wins = 0
    total = 0.0
    losses = []
    for _ in range(draws):
        price = spot * math.exp(mu + sd * rng.gauss(0.0, 1.0))
        pnl = pnl_at_expiry(legs, price)
        total += pnl
        if pnl > 0:
            wins += 1
        else:
            losses.append(pnl)
    return {
        "pop": wins / draws,
        "expected_pnl": total / draws,
        "p_loss": len(losses) / draws,
        "expected_loss": sum(losses) / len(losses) if losses else 0.0,
    }


@pytest.mark.parametrize("legs,label", [
    ([Leg("call", +1, 5.0, strike=100.0)], "long call"),
    ([Leg("call", +1, 5.0, strike=100.0),
      Leg("call", -1, 2.5, strike=110.0)], "bull call spread"),
    ([Leg("put", -1, 2.0, strike=90.0), Leg("put", +1, 1.0, strike=85.0),
      Leg("call", -1, 2.0, strike=110.0),
      Leg("call", +1, 1.0, strike=115.0)], "iron condor"),
])
def test_closed_form_matches_monte_carlo(legs, label):
    spot, iv, days = 100.0, 0.25, 30.0
    mc = _monte_carlo(legs, spot, iv, days)

    pop = probability_of_profit(legs, spot, iv, days)
    assert pop == pytest.approx(mc["pop"], abs=0.01), (
        "{}: probability of profit disagrees with Monte Carlo".format(label))

    tails = tail_metrics(legs, spot, iv, days)
    assert tails["p_loss"] == pytest.approx(mc["p_loss"], abs=0.01), label
    assert tails["expected_pnl"] == pytest.approx(
        mc["expected_pnl"], abs=0.06), label
    assert tails["expected_loss"] == pytest.approx(
        mc["expected_loss"], abs=0.06), label


def test_distribution_helpers_refuse_unusable_inputs():
    legs = [Leg("call", +1, 5.0, strike=100.0)]
    assert probability_of_profit(legs, 100.0, None, 30.0) is None
    assert probability_of_profit(legs, 100.0, 0.25, 0) is None
    assert tail_metrics(legs, 100.0, 0.0, 30.0) is None


# ----------------------------------------------------------------- outlook

def test_expected_move_and_band():
    move = expected_move(100.0, 0.25, 365.0)
    assert move == pytest.approx(25.0)
    lo, hi = one_sd_band(100.0, 0.25, 365.0)
    assert (lo, hi) == pytest.approx((75.0, 125.0))


def test_classify_target_covers_all_five_directions():
    args = (100.0, 0.20, 90.0)
    spot, iv, days = args
    move = expected_move(spot, iv, days)
    assert classify_target(spot, spot + move * 1.5, iv, days) == \
        Outlook.STRONG_BULLISH
    assert classify_target(spot, spot + move * 0.6, iv, days) == \
        Outlook.MILD_BULLISH
    assert classify_target(spot, spot + move * 0.1, iv, days) == \
        Outlook.NEUTRAL
    assert classify_target(spot, spot - move * 0.6, iv, days) == \
        Outlook.MILD_BEARISH
    assert classify_target(spot, spot - move * 1.5, iv, days) == \
        Outlook.STRONG_BEARISH


# ---------------------------------------------------------------- playbook

def test_split_chain_accepts_both_shapes():
    chain = split_chain(_chain())
    assert chain["calls"] and chain["puts"]
    assert chain["calls"] == sorted(chain["calls"],
                                    key=lambda c: c["strike"])
    legacy = split_chain({"calls": chain["calls"], "puts": chain["puts"],
                          "spot": 100.0})
    assert legacy["spot"] == 100.0


def test_split_chain_without_spot_is_an_error():
    with pytest.raises(ValueError):
        split_chain({"contracts": []})


@pytest.mark.parametrize("name", [n for n, m in PLAYBOOK.items()
                                  if m["build"] is not None])
def test_every_buildable_strategy_produces_a_coherent_plan(name):
    chain = split_chain(_chain())
    plan = build(name, chain)
    if plan is None:
        pytest.skip("{} found no viable structure on the synthetic chain"
                    .format(name))
    assert plan["strategy"] == name
    assert plan["legs"]
    metrics = plan["analysis"]
    # The declared trade type must match the arithmetic, not the intent.
    assert metrics["trade_type"] == plan["trade_type"], (
        "{} is declared {} but its net cash is {}".format(
            name, plan["trade_type"], metrics["net_cash"]))
    assert metrics["max_gain"] > 0
    assert describe(plan).startswith(name)


def test_two_expiry_strategies_refuse_rather_than_improvise():
    chain = split_chain(_chain())
    for name in ("calendar_spread", "diagonal_spread"):
        with pytest.raises(NotImplementedError):
            build(name, chain)


def test_unknown_strategy_names_the_alternatives():
    with pytest.raises(KeyError) as excinfo:
        build("moon_shot", split_chain(_chain()))
    assert "iron_condor" in str(excinfo.value)


def test_recommend_matches_structures_to_the_view():
    strong_bull = [name for name, _, _ in recommend(Outlook.STRONG_BULLISH)]
    assert strong_bull[0] in ("long_call", "straddle", "strangle")
    assert "long_call" in strong_bull

    neutral_crush = [name for name, _, _ in
                     recommend(Outlook.NEUTRAL, vol_view="crush")]
    assert "iron_condor" in neutral_crush
    assert "straddle" not in neutral_crush

    # Without a known direction only the two-sided trades qualify.
    unknown = [name for name, _, _ in
               recommend(Outlook.NEUTRAL, direction_known=False)]
    assert set(unknown) <= {"straddle", "strangle", "protective_put"}


def test_covered_call_needs_the_underlying():
    without = [name for name, _, _ in recommend(Outlook.NEUTRAL)]
    with_stock = [name for name, _, _ in
                  recommend(Outlook.NEUTRAL, owns_underlying=True)]
    assert "covered_call" not in without
    assert "covered_call" in with_stock


# ---------------------------------------------------------------- friction

def test_friction_grades_a_tight_market_as_ok():
    legs = [Leg("call", +1, 5.0, strike=100.0,
                ref={"bid": 4.95, "ask": 5.05, "mid": 5.0,
                     "open_interest": 900, "volume": 300})]
    result = plan_friction(legs, net_cash=-5.0)
    assert result["verdict"] == "ok"
    assert result["round_trip"] == pytest.approx(0.05)


def test_friction_rejects_a_leg_with_no_bid():
    legs = [Leg("call", +1, 5.0, strike=100.0,
                ref={"bid": 0.0, "ask": 5.05, "mid": 2.5})]
    result = plan_friction(legs, net_cash=-5.0)
    assert result["verdict"] == "untradeable"
    assert "no bid" in result["reason"]


def test_friction_rejects_a_market_wider_than_the_limit():
    legs = [Leg("call", +1, 5.0, strike=100.0,
                ref={"bid": 3.0, "ask": 7.0, "mid": 5.0})]
    result = plan_friction(legs, net_cash=-5.0)
    assert result["verdict"] == "untradeable"
    assert "percent of its own mid" in result["reason"]


def test_friction_is_unknown_without_quotes_not_ok():
    legs = [Leg("call", +1, 5.0, strike=100.0, ref={})]
    result = plan_friction(legs, net_cash=-5.0)
    assert result["verdict"] == "unknown"
    assert result["round_trip"] is None


def test_depth_flags_are_advisory_not_blocking():
    legs = [Leg("call", +1, 5.0, strike=100.0,
                ref={"bid": 4.95, "ask": 5.05, "mid": 5.0,
                     "open_interest": 2, "volume": 0})]
    result = plan_friction(legs, net_cash=-5.0)
    assert result["verdict"] == "ok"
    assert len(result["depth_flags"]) == 2


def test_underlying_legs_are_excluded_from_option_friction():
    legs = [Leg("underlying", +1, 100.0),
            Leg("call", -1, 3.0, strike=105.0,
                ref={"bid": 2.95, "ask": 3.05, "mid": 3.0})]
    result = plan_friction(legs, net_cash=3.0)
    assert result["entry_cost"] == pytest.approx(0.025)


def test_butterfly_refuses_a_structure_that_cannot_profit():
    # A chain quoted so wide that the body is cheap relative to the wings
    # makes the butterfly cost more than the distance between its strikes.
    # The builder must return None rather than a dead structure.
    chain = split_chain(_chain())
    for contract in chain["calls"]:
        if contract["strike"] in (95.0, 105.0):
            contract["mid"] *= 3.0
    assert build("long_call_butterfly", chain) is None
