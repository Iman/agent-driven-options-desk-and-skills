"""Strategy comparison and ranking.

Copyright (C) 2026 Iman Samizadeh. Licensed under AGPL-3.0-only.
"""

import pytest

from optiondesk_engine.analytics.compare import rank_strategies, score_plan


def _plan(name, expected=1.0, max_loss=-10.0, pop=0.6, verdict="ok",
          degraded=False, reward_risk=1.5):
    return {
        "strategy": name,
        "analysis": {"trade_type": "credit", "net_cash": 2.0,
                     "max_gain": 5.0, "max_loss": max_loss,
                     "reward_risk": reward_risk, "breakevens": [95.0, 105.0]},
        "probability": {"profit": pop, "loss": 1 - pop,
                        "expected_pnl": expected, "expected_loss": -3.0},
        "friction": {"verdict": verdict, "reason": "measured",
                     "round_trip": 0.2},
        "net_greeks": {"delta": 0.1, "theta": -0.2, "vega": 3.0,
                       "gamma": 0.01},
        "meta": {"degraded": degraded},
    }


def test_ranking_is_by_expected_return_on_capital_at_risk():
    plans = [_plan("a", expected=1.0, max_loss=-10.0),   # 0.10
             _plan("b", expected=1.0, max_loss=-4.0),    # 0.25
             _plan("c", expected=0.5, max_loss=-10.0)]   # 0.05
    result = rank_strategies(plans)
    assert [r["strategy"] for r in result["ranked"]] == ["b", "a", "c"]
    assert result["leader"]["strategy"] == "b"
    assert result["leader"]["expected_return_on_risk"] == pytest.approx(0.25)
    assert result["margin_over_runner_up"] == pytest.approx(0.15)


def test_probability_breaks_ties():
    plans = [_plan("low", expected=1.0, max_loss=-10.0, pop=0.4),
             _plan("high", expected=1.0, max_loss=-10.0, pop=0.9)]
    assert rank_strategies(plans)["leader"]["strategy"] == "high"


def test_an_untradeable_structure_is_excluded_not_ranked():
    plans = [_plan("rich", expected=9.0, max_loss=-2.0,
                   verdict="untradeable"),
             _plan("modest", expected=0.5, max_loss=-10.0)]
    result = rank_strategies(plans)
    # The excluded one has by far the best expectation, and is still not
    # the leader: an expectation you cannot enter is not an opportunity.
    assert result["leader"]["strategy"] == "modest"
    assert result["excluded_count"] == 1
    excluded = [r for r in result["rows"] if not r["rankable"]][0]
    assert any("untradeable" in reason
               for reason in excluded["excluded_because"])


def test_unbounded_loss_cannot_be_ranked_on_return_on_risk():
    plans = [_plan("naked", expected=2.0, max_loss="unlimited"),
             _plan("defined", expected=0.1, max_loss=-5.0)]
    result = rank_strategies(plans)
    assert result["leader"]["strategy"] == "defined"
    naked = [r for r in result["rows"] if r["strategy"] == "naked"][0]
    assert naked["capital_at_risk"] is None
    assert any("unbounded" in reason for reason in naked["excluded_because"])


def test_a_degraded_plan_is_flagged_even_when_it_ranks():
    result = rank_strategies([_plan("shaky", degraded=True)])
    row = result["rows"][0]
    assert any("degraded" in reason for reason in row["excluded_because"])


def test_no_rankable_structures_gives_no_leader():
    result = rank_strategies([_plan("bad", verdict="untradeable")])
    assert result["leader"] is None
    assert result["ranked"] == []
    assert result["rankable_count"] == 0


def test_the_caveat_travels_with_the_ranking():
    result = rank_strategies([_plan("a")])
    assert "not a recommendation" in result["caveat"]
    assert "measures that disagreement" in result["caveat"]
    assert result["criterion"]


def test_score_plan_survives_a_plan_missing_everything():
    row = score_plan({"strategy": "sparse"})
    assert row["strategy"] == "sparse"
    assert row["rankable"] is False
    assert row["capital_at_risk"] is None


# The finite check on the expectation itself was untested: mutation testing
# replaced it with a plain None check and the whole engine suite still
# passed. A NaN expectation then reaches the sort key, where comparisons
# are all false and the winner becomes whichever structure the list
# happened to start with.

def test_a_non_finite_expectation_is_not_rankable():
    for value in (float("nan"), float("inf"), float("-inf")):
        row = score_plan(_plan("odd", expected=value))
        assert not row["rankable"], (
            "an expectation of {} was ranked".format(value))
        assert any("finite" in reason for reason in row["excluded_because"]), (
            "nothing said why {} was excluded".format(value))


def test_a_nan_expectation_cannot_decide_the_winner():
    """Order dependence is the symptom that makes this worth a test.

    With NaN in the sort key every comparison is false, so the leader
    depends on the order the structures arrived in. The same set in a
    different order must give the same answer.
    """
    good = _plan("real", expected=1.0, max_loss=-10.0)
    broken = _plan("broken", expected=float("nan"), max_loss=-4.0)
    first = rank_strategies([broken, good])
    second = rank_strategies([good, broken])
    assert first["leader"]["strategy"] == "real"
    assert second["leader"]["strategy"] == "real"
    assert first["rankable_count"] == second["rankable_count"] == 1
    assert first["excluded_count"] == second["excluded_count"] == 1
