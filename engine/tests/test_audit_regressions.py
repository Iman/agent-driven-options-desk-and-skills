"""Regressions for defects found by adversarial audit.

Copyright (C) 2026 Iman Samizadeh. Licensed under AGPL-3.0-only.

Every test here uses the failing input the audit actually produced. They
are kept together rather than scattered because each one guards a claim
that a docstring made and the code did not honour, which is a specific
failure mode worth being able to re-run as a set.
"""

import math
import random

import pytest

from optiondesk_engine.analytics.compare import rank_strategies, score_plan
from optiondesk_engine.pricing.black_scholes import implied_vol
from optiondesk_engine.analytics.exposure import chain_exposure, max_pain
from optiondesk_engine.analytics.smile import smile_metrics
from optiondesk_engine.simulation.garch import _ess, _split_rhat
from optiondesk_engine.simulation.paths import terminal_risk
from optiondesk_engine.strategies.payoff import (
    Leg,
    analyze,
    probability_of_profit,
    tail_metrics,
)


# ------------------------------------------------------------------ payoff

@pytest.mark.parametrize("iv,days", [(16, 365), (17, 365), (58, 30),
                                     (20, 3650)])
def test_expectation_survives_a_saturated_cumulative(iv, days):
    """1 - cdf(lo) collapsed to zero and deleted the profitable region.

    A long call with an expected profit of 99.5 was reported as a 0.5
    expected loss with a probability of loss of 1.0, silently, once
    volatility times the square root of the horizon exceeded about 16.6.
    The survival function is now computed with erfc, which does not cancel.
    """
    legs = [Leg("call", +1, 0.5, strike=100.0)]
    result = tail_metrics(legs, 100.0, iv, days)
    assert result["expected_pnl"] == pytest.approx(99.5, rel=1e-6)


@pytest.mark.parametrize("spot,iv,days", [
    (100.0, float("nan"), 30.0),
    (100.0, 0.2, float("nan")),
    (float("nan"), 0.2, 30.0),
    (100.0, float("inf"), 30.0),
    (100.0, 0.2, float("inf")),
])
def test_non_finite_inputs_are_refused_not_propagated(spot, iv, days):
    """NaN defeated the guards: "not nan" and "nan <= 0" are both False.

    The result was a NaN probability alongside an expected loss of exactly
    0.0, which is the worst kind of wrong: one field screams and the other
    reads as a clean, reassuring number.
    """
    legs = [Leg("call", +1, 2.0, strike=100.0)]
    assert probability_of_profit(legs, spot, iv, days) is None
    assert tail_metrics(legs, spot, iv, days) is None


def test_a_structure_that_cannot_lose_has_no_reward_to_risk():
    """max_loss of +2.0 is a guaranteed minimum profit, not a risk.

    Dividing maximum gain by minimum gain and labelling it reward over risk
    produced 6.0 on a position that cannot lose, and the comparison then
    used it as a denominator.
    """
    legs = [Leg("call", +1, 1.0, strike=100.0),
            Leg("call", -1, 3.0, strike=110.0)]
    metrics = analyze(legs, spot=100.0)
    assert metrics["max_loss"] > 0
    assert metrics["risk_free"] is True
    assert metrics["reward_risk"] is None


# ----------------------------------------------------------------- compare

def _plan(name, expected, max_loss):
    return {"strategy": name,
            "analysis": {"trade_type": "credit", "net_cash": 1.0,
                         "max_gain": 5.0, "max_loss": max_loss,
                         "reward_risk": None, "breakevens": []},
            "probability": {"profit": 0.5, "loss": 0.5,
                            "expected_pnl": expected, "expected_loss": -1.0},
            "friction": {"verdict": "ok", "reason": "", "round_trip": 0.1},
            "net_greeks": {}, "meta": {}}


def test_an_infinite_loss_is_not_ranked_as_zero_risk():
    """The engine returns -inf; only the string "unlimited" was checked.

    A naked short call came through with capital at risk of infinity, an
    expected return on risk of exactly 0.0, and ranked above a defined-risk
    structure with a genuinely negative expectation.
    """
    row = score_plan(_plan("naked", 2.0, float("-inf")))
    assert row["capital_at_risk"] is None
    assert row["rankable"] is False
    assert any("unbounded" in reason for reason in row["excluded_because"])

    result = rank_strategies([_plan("naked", 2.0, float("-inf")),
                              _plan("defined", -0.5, -5.0)])
    assert result["leader"] is None or result["leader"]["strategy"] != "naked"


def test_a_non_finite_expectation_cannot_win_by_dict_order():
    """NaN compares False against everything, so sort left it where it fell.

    The leader, which is the field a user acts on, was decided by input
    order: the same three plans produced three different winners.
    """
    plans = [_plan("good", 1.0, -5.0), _plan("nanny", float("nan"), -5.0),
             _plan("ok", 0.5, -5.0)]
    leaders = set()
    for order in ([0, 1, 2], [1, 0, 2], [2, 1, 0]):
        result = rank_strategies([plans[i] for i in order])
        leaders.add(result["leader"]["strategy"])
        assert all(math.isfinite(row["expected_return_on_risk"])
                   for row in result["ranked"])
    assert leaders == {"good"}


def test_a_risk_free_structure_is_excluded_for_the_right_reason():
    row = score_plan(_plan("cannot lose", 1.0, 2.0))
    assert row["rankable"] is False
    assert any("worst outcome is a profit" in reason
               for reason in row["excluded_because"])


# ---------------------------------------------------------------- exposure

def test_every_gamma_flip_crossing_is_reported():
    """Reporting only the first crossing put the level 18 percent away.

    At spot 100 with crossings at 81.7, 87.5, 92.2, 96.8 and 102.5, the
    old code returned 81.67 and said nothing about the other four. It is
    drawn on the chart as a level, so a reader concluded there was a long
    way to go before the regime changed.
    """
    contracts = []
    for strike, gamma, kind, oi in ((80, 0.02, "put", 500),
                                    (85, 0.05, "call", 900),
                                    (90, 0.06, "put", 900),
                                    (95, 0.07, "call", 1000),
                                    (100, 0.09, "put", 1200),
                                    (105, 0.09, "call", 1300)):
        contracts.append({"type": kind, "strike": float(strike),
                          "gamma": gamma, "open_interest": oi, "volume": 10})
    result = chain_exposure(contracts, spot=100.0)
    assert len(result["gamma_flip_all"]) >= 2
    nearest = min(result["gamma_flip_all"], key=lambda x: abs(x - 100.0))
    assert result["gamma_flip"] == pytest.approx(nearest)
    assert "nearest spot" in result["gamma_flip_note"]


def test_a_chain_with_no_calls_has_no_call_wall():
    """max() over all-zero call gamma returned the first row as the wall."""
    contracts = [{"type": "put", "strike": 90.0, "gamma": 0.03,
                  "open_interest": 500, "volume": 5},
                 {"type": "put", "strike": 95.0, "gamma": 0.04,
                  "open_interest": 900, "volume": 5}]
    result = chain_exposure(contracts, spot=100.0)
    assert result["call_wall"] is None
    assert result["put_wall"]["strike"] == 95.0


def test_max_pain_from_no_open_interest_is_refused():
    """Every strike pays zero, so the minimum fell on the lowest strike."""
    contracts = [{"type": "call", "strike": 90.0, "open_interest": 0},
                 {"type": "put", "strike": 100.0, "open_interest": 0}]
    assert max_pain(contracts) is None


# ------------------------------------------------------------------- smile

def test_wings_are_absent_when_the_chain_does_not_reach_them():
    """A 45-delta chain reported a "25-delta" risk reversal of 0.09.

    The strikes it used were one point either side of spot. The label said
    25 delta and nothing in the output disagreed.
    """
    rows = [{"type": "call", "strike": 101.0, "delta": 0.45, "iv": 0.21},
            {"type": "put", "strike": 99.0, "delta": -0.45, "iv": 0.30}]
    metrics = smile_metrics(rows, spot=100.0, days=30)
    assert metrics["risk_reversal"] is None
    assert metrics["butterfly"] is None
    assert metrics["call_wing"] is None and metrics["put_wing"] is None
    assert metrics["atm_iv"] is not None


def test_at_the_money_volatility_does_not_depend_on_row_order():
    """A tie between a call and a put swung expected move by 50 percent."""
    call = {"type": "call", "strike": 100.0, "delta": 0.5, "iv": 0.20}
    put = {"type": "put", "strike": 100.0, "delta": -0.5, "iv": 0.30}
    first = smile_metrics([call, put], spot=100.0, days=30)
    second = smile_metrics([put, call], spot=100.0, days=30)
    assert first["atm_iv"] == second["atm_iv"] == pytest.approx(0.20)
    assert first["atm_type"] == "call"
    assert first["expected_move"] == pytest.approx(second["expected_move"])


def test_the_expected_range_never_goes_below_zero():
    """An arithmetic band on a lognormal reached minus fifty."""
    rows = [{"type": "call", "strike": 100.0, "delta": 0.5, "iv": 1.5}]
    metrics = smile_metrics(rows, spot=100.0, days=365)
    assert metrics["expected_range"][0] == 0.0
    assert metrics["expected_range_floored"] is True


# -------------------------------------------------------------- simulation

def test_a_stuck_chain_is_not_certified_as_converged():
    """Two chains parked on the same point passed every gate.

    R-hat came back None on zero within-chain variance and was treated as a
    pass, and the effective sample size estimator returned the full draw
    count. A sampler that never accepted a proposal was reported as
    converged with a perfect effective sample size.
    """
    frozen = [[1.0] * 500, [1.0] * 500]
    assert _split_rhat(frozen) == float("inf")
    assert _ess([1.0] * 500) == 1.0


def test_risk_refuses_a_non_finite_distribution():
    """probability_up counted r > 0, which is False for NaN, giving 0.0."""
    nan = float("nan")
    simulation = {"terminal": [nan, nan, nan], "spot": 100.0,
                  "horizon_days": 5, "paths": 3}
    assert terminal_risk(simulation) is None


def test_a_tail_of_one_path_is_flagged_rather_than_reported():
    """With ten paths the 99 percent index floors onto the worst one.

    Value at risk then equals expected shortfall exactly, which looks like
    a number and is not one.
    """
    simulation = {"terminal": sorted(float(100 + i) for i in range(10)),
                  "spot": 100.0, "horizon_days": 5, "paths": 10}
    risk = terminal_risk(simulation)
    assert risk["insufficient_paths"]
    assert any("tail holds 1 path" in message
               for message in risk["insufficient_paths"])


def test_risk_levels_do_not_collide_in_their_keys():
    """int(level * 100) mapped 0.999 and 0.9999 both onto var_99."""
    simulation = {"terminal": sorted(100.0 + i * 0.01 for i in range(5000)),
                  "spot": 100.0, "horizon_days": 5, "paths": 5000}
    risk = terminal_risk(simulation, levels=(0.99, 0.999, 0.9999))
    keys = {key for key in risk if key.startswith("var_")}
    assert keys == {"var_99", "var_99_9", "var_99_99"}


# ------------------------------------------------------- the second guard

# implied_vol has two identifiability guards, one before the iteration and
# one inside it, and only the first was tested. Mutation testing removed
# the inner one and the entire engine suite still passed. Without it, 39 of
# 450 sampled inputs raise ZeroDivisionError and 94 return a volatility for
# a price that identifies none: a one cent deep out of the money put comes
# back at 254 percent, and a call trading at intrinsic at 386 percent.

CRASHES_WITHOUT_THE_INNER_GUARD = [
    # spot, strike, years, kind, price
    (100.0, 10.0, 0.002, "call", 90.01),
    (100.0, 10.0, 0.002, "call", 90.05),
    (100.0, 10.0, 0.002, "put", 0.000001),
    (100.0, 10.0, 0.002, "put", 0.0001),
    (100.0, 10.0, 0.002, "put", 0.01),
]

INVENTS_A_NUMBER_WITHOUT_THE_INNER_GUARD = [
    (100.0, 10.0, 0.05, "call", 90.05),
    (100.0, 10.0, 0.05, "put", 0.0001),
    (100.0, 10.0, 0.05, "put", 0.01),
    (100.0, 10.0, 0.25, "put", 0.0001),
]


def test_the_inner_vega_guard_refuses_rather_than_dividing_by_zero():
    """Newton's step divides by vega, and vega reaches zero on these.

    The guard has to sit inside the loop as well as before it, because a
    price whose vega is usable at the seed can still drive the iteration
    into a region where the curve is flat.
    """
    for spot, strike, t, kind, price in CRASHES_WITHOUT_THE_INNER_GUARD:
        assert implied_vol(price, spot, strike, t, kind) is None, (
            "{} {} at {} should be refused".format(kind, strike, price))


def test_the_inner_vega_guard_refuses_rather_than_inventing_a_volatility():
    """A flat curve gives bisection an arbitrary point to land on.

    Each of these returned a plausible looking volatility, between 114 and
    409 percent, from a price that identifies no volatility at all.
    """
    for spot, strike, t, kind, price in INVENTS_A_NUMBER_WITHOUT_THE_INNER_GUARD:
        assert implied_vol(price, spot, strike, t, kind) is None, (
            "{} {} at {} should be refused".format(kind, strike, price))
