"""The composite support score: the arithmetic, the gates, the omissions.

Copyright (C) 2026 Iman Samizadeh. Licensed under the PolyForm Noncommercial License 1.0.0.

WHAT WOULD BREAK. This module is a port. A port is exactly the kind of code
that looks right and is wrong by a factor, a sign or an order of
operations, because the reviewer reads it against their memory of the
original rather than against the original. So the first test computes a
score by hand in its docstring and asserts the number, and the rest pin
each branch that the formula's prose promises: the friction gate, the thin
multiplier, the volatility tilt in both directions, and the unbounded gain.

The inputs throughout are chosen so that every intermediate and the total
are exactly representable in binary floating point. That was checked before
these tests were written, by evaluating the expression and comparing with
==; it is why the assertions can be exact rather than approximate. Change
an input and the exactness is not guaranteed to survive.
"""

import pytest

from optiondesk_engine.analytics.ranking import (
    MIN_ABS_PREMIUM,
    RR_CAP,
    SCORE_WEIGHTS,
    THIN_MULTIPLIER,
    VRP_TILT,
    is_unbounded,
    missing_inputs,
    rank_rows,
    row_from_comparison,
    score_row,
)


def _row(**overrides):
    """One structure whose components all land on exact binary fractions."""
    row = {
        "structure": "worked_example",
        "trade_type": "debit",
        "net_cash": -2.00,
        "max_gain": 4.50,
        "max_loss": -2.00,
        "reward_risk": 2.25,
        "pop": 0.75,
        "expected_pnl": 0.75,
        "expected_shortfall": -1.00,
        "friction": {"verdict": "ok", "round_trip": 0.25,
                     "reason": "round trip is 12.5 percent of the premium"},
    }
    row.update(overrides)
    return row


# --------------------------------------------------------- the arithmetic

def test_the_worked_example_scores_exactly_sixty_seven_point_five():
    """The whole formula, computed by hand, on the row above.

    A debit structure paying 2.00, worth 4.50 at best and losing the 2.00
    at worst, 75 percent likely to profit, expected to make 0.75 against a
    round trip of 0.25, with an average loss of 1.00 across the losing
    outcomes.

        premium    = max(|-2.00|, 0.05)             = 2.00
        edge_after = 0.75 - 0.25                    = 0.50
        e          = clamp(0.50 / 2.00, -1, 1)      = 0.25
        edge       = (0.25 + 1) / 2                 = 0.625
        rr         = min(2.25, 3.0) / 3.0           = 0.75
        worst      = |-2.00|                        = 2.00
        es         = min(|-1.00| / 2.00, 1.0)       = 0.50

        score = 100 * (0.30 * 0.750      pop
                     + 0.30 * 0.625      edge
                     + 0.25 * 0.750      rr
                     + 0.15 * 0.500)     1 - es
              = 100 * (0.2250 + 0.1875 + 0.1875 + 0.0750)
              = 100 * 0.675
              = 67.5

    The volatility view is neutral, so the tilt is zero, and the friction
    verdict is ok, so the thin multiplier is 1.0. Neither touches the
    total.
    """
    score, parts = score_row(_row())

    assert score == 67.5

    assert parts["pop_norm"] == 0.75
    assert parts["edge_norm"] == 0.625
    assert parts["rr_norm"] == 0.75
    assert parts["es_norm"] == 0.5
    assert parts["premium"] == 2.0
    assert parts["edge_after_friction"] == 0.5
    assert parts["worst_case"] == 2.0
    assert parts["base_score"] == 67.5
    assert parts["vrp_tilt"] == 0.0
    assert parts["thin_multiplier"] == 1.0
    assert parts["substituted"] == []


def test_the_four_components_are_returned_so_the_score_can_be_argued_with():
    """A composite whose parts are hidden can only be believed or ignored."""
    _, parts = score_row(_row())
    assert set(SCORE_WEIGHTS) == {"pop", "edge", "rr", "es"}
    assert parts["weights"] == SCORE_WEIGHTS
    # And the returned weights must be a copy: a caller that edited them
    # would silently reweight every later score in the process.
    parts["weights"]["pop"] = 0.99
    assert SCORE_WEIGHTS["pop"] == 0.30


def test_the_edge_term_is_after_friction_not_before_it():
    """Friction is the only part of this that touches the cost of trading.

    Subtracting it is the whole reason the term is called edge rather than
    expectation. With the round trip at zero the same row scores higher,
    and the difference is exactly the weight on the edge term.
    """
    with_friction, _ = score_row(_row())
    without, parts = score_row(_row(
        friction={"verdict": "ok", "round_trip": 0.0, "reason": "free"}))
    assert parts["edge_norm"] == 0.6875   # (0.75 / 2.00 + 1) / 2
    assert without > with_friction
    assert without == pytest.approx(
        with_friction + 100.0 * SCORE_WEIGHTS["edge"] * 0.0625)


def test_the_edge_term_is_clamped_at_both_ends():
    """An expectation many times the premium must not run away with the score.

    Without the clamp a structure whose model expectation is ten times what
    it costs contributes ten times the intended weight, and the composite
    stops being a number out of 100.
    """
    _, high = score_row(_row(expected_pnl=100.0))
    _, low = score_row(_row(expected_pnl=-100.0))
    assert high["edge_norm"] == 1.0
    assert low["edge_norm"] == 0.0


def test_the_premium_floor_stops_quote_noise_inflating_the_edge():
    """A structure priced at a cent divides by the floor, not by the cent."""
    _, parts = score_row(_row(net_cash=-0.01))
    assert parts["premium"] == MIN_ABS_PREMIUM


def test_reward_to_risk_is_capped_rather_than_rewarded_without_limit():
    """Past the cap the ratio measures distance to the strike, which the
    probability term is already measuring."""
    _, at_cap = score_row(_row(max_gain=30.0, reward_risk=RR_CAP))
    _, far_past = score_row(_row(max_gain=300.0, reward_risk=RR_CAP * 20))
    assert at_cap["rr_norm"] == 1.0
    assert far_past["rr_norm"] == 1.0


def test_the_expected_shortfall_term_is_capped_at_the_whole_worst_case():
    """A structure whose average loss is its entire worst case scores zero
    on the term, never a negative contribution."""
    _, parts = score_row(_row(expected_shortfall=-50.0))
    assert parts["es_norm"] == 1.0


# ------------------------------------------------------- unbounded gain

def test_an_unbounded_gain_scores_the_reward_term_outright():
    """A long call has no reward:risk ratio, and scoring it zero for want of
    a denominator would put it below every spread on the board.

    Same row as the worked example with the gain unbounded and the ratio
    therefore absent, so rr goes from 0.750 to 1.000:

        score = 100 * (0.30 * 0.750 + 0.30 * 0.625
                     + 0.25 * 1.000 + 0.15 * 0.500)
              = 100 * (0.2250 + 0.1875 + 0.2500 + 0.0750)
              = 73.75
    """
    for sentinel in ("unlimited", float("inf")):
        score, parts = score_row(_row(max_gain=sentinel, reward_risk=None))
        assert parts["rr_norm"] == 1.0, sentinel
        assert score == 73.75, sentinel
        # An absent ratio that was never used is not a substitution, so
        # nothing should be reported as having stood in for it.
        assert parts["substituted"] == [], sentinel


def test_an_unbounded_loss_measures_the_shortfall_against_the_premium():
    """There is no worst case to divide by, so something has to stand in.

    Using the premium is a choice and not a measurement, so the row says
    so. A silent substitution here would make a naked short look as though
    its shortfall had been measured against a real worst case.
    """
    score, parts = score_row(_row(net_cash=-4.00, max_loss="unlimited",
                                  max_gain=6.00, reward_risk=None))
    assert parts["worst_case"] == 4.0
    assert parts["es_norm"] == 0.25       # |-1.00| / 4.00
    assert score is not None
    assert any("unbounded" in note for note in parts["substituted"])
    assert any("reward to risk" in note for note in parts["substituted"])


def test_is_unbounded_recognises_both_the_float_and_the_serialised_string():
    """The engine writes an infinity; the shell writes the word.

    Reading only the string let an infinity through as a finite figure once
    already, in compare._risk_capital, where it ranked a naked short call
    above a defined-risk structure.
    """
    assert is_unbounded(float("inf"))
    assert is_unbounded(float("-inf"))
    assert is_unbounded("unlimited")
    assert is_unbounded("UNLIMITED")
    assert not is_unbounded(0.0)
    assert not is_unbounded(-12.5)
    assert not is_unbounded(None)


# ------------------------------------------------------- the friction gate

@pytest.mark.parametrize("verdict", ["untradeable", "unknown"])
def test_an_excluding_verdict_takes_the_row_out_of_the_ranking(verdict):
    """An expectation that cannot be entered is not an opportunity.

    The row is still returned, carrying the reason, because a leaderboard
    that hides what it dropped reports a different set of structures than
    the one it was given.
    """
    score, exclusion = score_row(_row(
        friction={"verdict": verdict, "round_trip": 0.25,
                  "reason": "a leg has no bid"}))
    assert score is None
    assert exclusion["excluded"] == verdict
    assert exclusion["reason"] == "a leg has no bid"


def test_an_excluded_structure_is_excluded_however_good_it_looks():
    """The whole point of the gate: the best-looking row can be the dropped
    one, and the ranking must not quietly keep it."""
    brilliant = _row(structure="cannot_be_entered", expected_pnl=100.0,
                     pop=0.99,
                     friction={"verdict": "untradeable", "round_trip": 9.0,
                               "reason": "round trip is 450 percent of the "
                                         "premium"})
    ordinary = _row(structure="ordinary")
    ranked, rejected = rank_rows([brilliant, ordinary])
    assert [row["structure"] for row in ranked] == ["ordinary"]
    assert [row["structure"] for row in rejected] == ["cannot_be_entered"]
    assert "450 percent" in rejected[0]["exclusion"]["reason"]


def test_a_row_with_no_friction_verdict_at_all_is_not_scored():
    """A multi-expiry structure carries no single-expiry friction verdict.

    That is a different statement from "friction is fine", and treating the
    absence as fine would put every calendar and diagonal into the ranking
    on an axis that subtracts a cost nobody estimated.
    """
    score, exclusion = score_row(_row(friction={}))
    assert score is None
    assert exclusion["excluded"] == "no friction verdict"
    assert "friction verdict" in exclusion["missing"]


# ---------------------------------------------------------- missing inputs

@pytest.mark.parametrize("field", ["pop", "net_cash", "expected_pnl",
                                   "expected_shortfall", "max_gain",
                                   "max_loss", "trade_type"])
def test_a_structure_missing_an_input_is_not_scored_as_if_it_had_it(field):
    """Each required input, absent one at a time, must stop the score.

    Scoring on the inputs that are present is scoring the structure as
    though the absent one were favourable, and nothing on the page would
    say which one was invented.
    """
    score, exclusion = score_row(_row(**{field: None}))
    assert score is None, "{} was scored while absent".format(field)
    assert exclusion["excluded"] == "missing inputs"
    assert exclusion["missing"] == [field]
    assert field in exclusion["reason"]


def test_a_nan_input_counts_as_absent_rather_than_as_a_number():
    """NaN defeats the obvious guard and then poisons the sort.

    "value is not None" is true of NaN and every comparison against it is
    false, so a NaN probability produces a NaN score whose position in the
    ordering depends on the order the structures arrived in.
    """
    score, exclusion = score_row(_row(pop=float("nan")))
    assert score is None
    assert exclusion["missing"] == ["pop"]
    assert missing_inputs(_row(expected_pnl=float("nan"))) == ["expected_pnl"]


def test_every_absent_input_is_named_not_just_the_first():
    """A reader fixing one omission should not have to run it again to
    discover the next."""
    absent = missing_inputs(_row(pop=None, expected_pnl=None, max_loss=None))
    assert absent == ["pop", "expected_pnl", "max_loss"]


def test_an_absent_round_trip_is_substituted_and_said_so():
    """The verdict is not "unknown", so friction was estimated; a round trip
    that is still absent means zero cost was assumed, which flatters the
    edge term and must be visible on the row."""
    score, parts = score_row(_row(
        friction={"verdict": "ok", "round_trip": None, "reason": "measured"}))
    assert score is not None
    assert parts["round_trip"] == 0.0
    assert any("round trip" in note for note in parts["substituted"])


# ------------------------------------------------------ the thin multiplier

def test_a_thin_friction_verdict_multiplies_the_whole_score_down():
    """The friction module's own wording is that a modelled advantage should
    be treated as halved on a thin verdict. This is that statement applied
    to the composite, and it is not optional.

        67.5 * 0.75 = 50.625
    """
    score, parts = score_row(_row(
        friction={"verdict": "thin", "round_trip": 0.25,
                  "reason": "round trip is 12.5 percent of the premium"}))
    assert parts["thin_multiplier"] == THIN_MULTIPLIER
    assert parts["base_score"] == 67.5
    assert score == 50.625


def test_the_thin_multiplier_applies_after_the_tilt_not_before_it():
    """Order of operations, which is exactly what a port gets wrong.

    The source adds the tilt to the base and then scales the total, so a
    thin structure loses a quarter of its tilt as well as a quarter of its
    measurements. Scaling first and then adding the tilt would give
    50.625 - 5.0 = 45.625 instead.

        (67.5 - 5.0) * 0.75 = 62.5 * 0.75 = 46.875
    """
    score, _ = score_row(_row(
        friction={"verdict": "thin", "round_trip": 0.25, "reason": "thin"}),
        vol_view="crush")
    assert score == 46.875


# ----------------------------------------------------------- the VRP tilt

def test_a_crush_view_favours_credit_and_penalises_debit():
    """Selling premium into a volatility that is expected to fall.

        debit  67.5 - 5.0 = 62.5
        credit 67.5 + 5.0 = 72.5
    """
    debit, debit_parts = score_row(_row(trade_type="debit"),
                                   vol_view="crush")
    credit, credit_parts = score_row(_row(trade_type="credit"),
                                     vol_view="crush")
    assert debit_parts["vrp_tilt"] == -VRP_TILT
    assert credit_parts["vrp_tilt"] == VRP_TILT
    assert debit == 62.5
    assert credit == 72.5


def test_an_expand_view_reverses_the_tilt_exactly():
    """The mirror of the case above, and the test that catches an inversion.

        debit  67.5 + 5.0 = 72.5
        credit 67.5 - 5.0 = 62.5
    """
    debit, debit_parts = score_row(_row(trade_type="debit"),
                                   vol_view="expand")
    credit, credit_parts = score_row(_row(trade_type="credit"),
                                     vol_view="expand")
    assert debit_parts["vrp_tilt"] == VRP_TILT
    assert credit_parts["vrp_tilt"] == -VRP_TILT
    assert debit == 72.5
    assert credit == 62.5


def test_a_neutral_view_moves_nothing_in_either_direction():
    """The default has to be inert, or every score on the dashboard carries
    an opinion nobody stated."""
    for trade_type in ("credit", "debit"):
        score, parts = score_row(_row(trade_type=trade_type))
        assert parts["vrp_tilt"] == 0.0
        assert score == 67.5


def test_the_tilt_cannot_push_a_score_outside_nought_to_a_hundred():
    """A 0 to 100 scale that reports 103 is not a 0 to 100 scale."""
    top = _row(pop=1.0, expected_pnl=100.0, max_gain="unlimited",
               reward_risk=None, expected_shortfall=0.0, trade_type="credit")
    bottom = _row(pop=0.0, expected_pnl=-100.0, max_gain=0.0, reward_risk=0.0,
                  expected_shortfall=-100.0, trade_type="debit")
    assert score_row(top, vol_view="crush")[0] == 100.0
    assert score_row(bottom, vol_view="crush")[0] == 0.0


# ------------------------------------------------------------- the ordering

def test_rank_rows_orders_by_score_and_numbers_from_one():
    middle = _row(structure="middle")
    best = _row(structure="strongest", pop=0.95)
    worst = _row(structure="weakest", pop=0.10)
    ranked, rejected = rank_rows([middle, worst, best])
    assert [row["structure"] for row in ranked] == ["strongest", "middle",
                                                    "weakest"]
    assert [row["rank"] for row in ranked] == [1, 2, 3]
    assert rejected == []


def test_two_identical_scores_do_not_swap_places_between_runs():
    """An ordering that is not a function of its input is not an ordering.

    Without the name in the sort key the two rows keep whichever order the
    list happened to arrive in, and the leader changes when the caller
    iterates a set or a directory in a different order.
    """
    first = rank_rows([_row(structure="beta"), _row(structure="alpha")])[0]
    second = rank_rows([_row(structure="alpha"), _row(structure="beta")])[0]
    assert [row["structure"] for row in first] == ["alpha", "beta"]
    assert [row["structure"] for row in second] == ["alpha", "beta"]


def test_the_top_argument_limits_the_ranking_and_not_the_rejections():
    """Truncating the rejections would hide exactly the rows a reader most
    needs to know were considered and dropped."""
    rows = [_row(structure="s{}".format(i), pop=i / 10.0) for i in range(6)]
    rows += [_row(structure="out{}".format(i),
                  friction={"verdict": "untradeable", "round_trip": 1.0,
                            "reason": "no bid"}) for i in range(3)]
    ranked, rejected = rank_rows(rows, top=2)
    assert len(ranked) == 2
    assert len(rejected) == 3


# ------------------------------------------- the comparison-artifact adapter

def test_the_adapter_maps_a_comparison_row_without_inventing_anything():
    """The artifact is flat and names three fields differently.

    expected_loss is the expected shortfall, friction_cost is the round
    trip, and the friction reason was flattened into excluded_because when
    the artifact was written.
    """
    artifact_row = {
        "strategy": "iron_condor", "trade_type": "credit", "net_cash": 3.32,
        "max_gain": 3.32, "max_loss": -16.68, "reward_risk": 0.199,
        "probability_of_profit": 0.7244, "expected_pnl": -0.6971,
        "expected_loss": -10.9979, "friction_verdict": "ok",
        "friction_cost": 0.03, "excluded_because": ["built from a degraded "
                                                    "snapshot"],
    }
    row = row_from_comparison(artifact_row)
    assert row["structure"] == "iron_condor"
    assert row["pop"] == 0.7244
    assert row["expected_shortfall"] == -10.9979
    assert row["friction"]["round_trip"] == 0.03
    assert row["friction"]["verdict"] == "ok"
    assert "degraded" in row["friction"]["reason"]
    assert score_row(row)[0] is not None


def test_the_adapter_leaves_a_multi_expiry_row_unscorable():
    """The calendars and diagonals in a comparison artifact carry nulls for
    the single-expiry probability and no friction verdict at all. The
    adapter must pass that absence through rather than filling it."""
    row = row_from_comparison({
        "strategy": "calendar_spread", "trade_type": "debit",
        "net_cash": -12.88, "max_gain": 9.03, "max_loss": -12.88,
        "reward_risk": 0.701, "probability_of_profit": None,
        "expected_pnl": None, "expected_loss": None,
        "friction_verdict": None, "friction_cost": None,
    })
    assert row["friction"] == {}
    score, exclusion = score_row(row)
    assert score is None
    assert exclusion["excluded"] == "no friction verdict"
    assert "pop" in exclusion["missing"]
