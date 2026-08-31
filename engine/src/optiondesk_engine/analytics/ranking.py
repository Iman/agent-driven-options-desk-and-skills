"""Composite support score: one number per structure, under a printed formula.

Copyright (C) 2026 Iman Samizadeh. Licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate written agreement.
Ported from smartsheep.witty.strategies.spreads.spread_engine, functions
score_row and rank_rows and the constants they read.

WHY THIS EXISTS. compare.py already orders structures, on one criterion:
model expected profit per unit of capital at risk. One criterion is easy to
audit and easy to game, because a structure can look excellent on it while
being a coin flip, or while paying its entire expectation to the spread.
This module puts four measured quantities on one axis instead, with the
weights written down, so a reader who disagrees with the ordering can point
at the component they disagree with rather than at the number.

WHAT IT REFUSES TO CLAIM, and this is the whole point of the module. The
score is a weighted sum of four figures that a reader can inspect. It is
not an estimate of edge, not a forecast, and not a statement that the
highest number is the one to trade. All four inputs come from the same
lognormal model at one at-the-money volatility, so three of the four move
together and the composite is nowhere near as independent as four terms
suggest. A structure ranks above another under these weights; under other
weights it would not, and no weighting here was fitted to anything.

THE FORMULA, printed with every use of it:

    score = 100 * (0.30 pop + 0.30 edge + 0.25 rr + 0.15 (1 - es))

    pop   model probability of profit, already on [0, 1]
    edge  friction-adjusted expected P/L per unit premium, clamped to
          [-1, 1] and mapped onto [0, 1], so 0.5 is "pays exactly its own
          friction" rather than "no information"
    rr    reward to risk, capped at RR_CAP and divided by it; an unbounded
          maximum gain scores 1.0 outright
    es    expected shortfall as a fraction of the worst case, so the term
          enters as (1 - es) and a structure whose average loss is its
          whole worst case contributes nothing

    then a VRP tilt of plus or minus VRP_TILT points, credit families
    favoured when volatility is expected to crush and debit families when
    it is expected to expand, and a THIN_MULTIPLIER on the whole score when
    the friction verdict is "thin". The result is clamped to [0, 100].

A friction verdict of "untradeable" or "unknown" excludes the row from the
ranking entirely. It is returned in the rejected list carrying its reason,
never dropped, because a structure that cannot be entered is not an
opportunity and a reader still needs to know it was considered.

THREE DEPARTURES FROM THE SOURCE, all deliberate and the first two visible
in the output rather than only here:

  1. The source assumes every input is present and would raise on a row
     that is missing one. Artifacts in this project legitimately carry
     nulls: a multi-expiry structure has no single-expiry probability and
     no friction verdict at all. Such a row is excluded and the absent
     inputs are named, rather than being scored as though it had them.
  2. The source compares maximum gain and loss against float infinity. The
     shell serialises an unbounded figure to the string "unlimited", so
     both the float and the string are recognised here. Missing this would
     have sent abs("unlimited") into the arithmetic.
  3. The source sorts on score alone. Two structures that score identically
     then keep whichever order the caller's list happened to be in, so the
     leader changes when the same artifacts are iterated differently. The
     structure name breaks the tie here, which makes the ordering a
     function of its input.

No I/O, no file reads, standard library only.
"""

import math

# The published weights. They sum to 1.0, which is what makes the score a
# number out of 100 rather than an arbitrary total.
SCORE_WEIGHTS = {"pop": 0.30, "edge": 0.30, "rr": 0.25, "es": 0.15}

# Reward to risk above this is not rewarded further. Past roughly three to
# one the figure is dominated by how far out the short strike is, which the
# probability term is already measuring, so an uncapped ratio would count
# the same fact twice.
RR_CAP = 3.0

# Points added or removed for a stated view on volatility. Deliberately
# small against a 0 to 100 scale: a view is an opinion, and it should be
# able to break a tie without being able to overturn the measurements.
VRP_TILT = 5.0

# What survives a friction verdict of "thin". The friction module's own
# wording is that the edge has to be real to survive it and any modelled
# advantage should be treated as halved; this is the same statement applied
# to the composite.
THIN_MULTIPLIER = 0.75

# A floor on the premium the edge term divides by, so a structure priced at
# quote noise cannot produce an enormous edge from a rounding error.
MIN_ABS_PREMIUM = 0.05

# Friction verdicts that take a row out of the ranking altogether.
EXCLUDING_VERDICTS = ("untradeable", "unknown")

# What the shell writes where the engine had a float infinity.
UNBOUNDED = "unlimited"

# Inputs without which no score can be computed. reward_risk is absent from
# this list on purpose: it is genuinely undefined for a structure with an
# unbounded gain or no possible loss, and the formula has a defined
# behaviour for that. Its absence is reported as a substitution instead.
REQUIRED_INPUTS = ("pop", "net_cash", "expected_pnl", "expected_shortfall",
                   "max_gain", "max_loss", "trade_type")

FORMULA = ("score = 100 * (0.30 pop + 0.30 edge + 0.25 rr + 0.15 (1 - es)), "
           "then a VRP tilt of plus or minus 5.0 points and a 0.75 "
           "multiplier on a thin friction verdict, clamped to 0 to 100")

VOL_VIEWS = ("neutral", "crush", "expand")


def is_unbounded(value):
    """True for an infinite figure however it reached us.

    The engine produces float("inf") and float("-inf"); the shell writes
    the string "unlimited" into artifacts. Both mean the same thing and
    both arrive here, depending on whether the caller is holding a live
    plan or a file that was read back.
    """
    if isinstance(value, str):
        return value.strip().lower() == UNBOUNDED
    if isinstance(value, (int, float)):
        return not math.isfinite(float(value))
    return False


def _number(value):
    """A finite float, or None. NaN is not a number for this purpose.

    NaN defeats the obvious guard, exactly as it does in payoff._usable:
    "value is not None" is true and "value <= 0" is false, so a NaN
    probability would pass straight through and produce a NaN score that
    then sorts unpredictably against every real one.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def missing_inputs(row):
    """The names of the required inputs this row does not carry.

    Returned in the order of REQUIRED_INPUTS so two rows missing the same
    things read the same way on the page.
    """
    absent = []
    for name in REQUIRED_INPUTS:
        value = row.get(name)
        if name == "trade_type":
            if not value:
                absent.append(name)
            continue
        if name in ("max_gain", "max_loss") and is_unbounded(value):
            continue
        if _number(value) is None:
            absent.append(name)
    return absent


def score_row(row, vol_view="neutral"):
    """(score, components) under the printed formula, or (None, exclusion).

    A score of None is not a failure and not a zero. It says the row was
    considered and left out, and the second element then carries "excluded",
    "reason" and "missing" so the page can say which.
    """
    friction = row.get("friction") or {}
    verdict = friction.get("verdict")
    absent = missing_inputs(row)

    # A structure the comparison would not rank is not ranked here either.
    # Two panels of one dashboard disagreed about the ratio spread: the
    # comparison excluded it because return on risk has no denominator when
    # the loss is unbounded, and this module scored it at rank 17 by
    # substituting the premium for the worst case. Both answers were
    # defensible on their own and the pair was not.
    if row.get("rankable") is False:
        return None, {
            "excluded": "not rankable in the comparison",
            "reason": (row.get("friction", {}).get("reason")
                       or "the comparison beside this one excludes it, and "
                          "one page cannot rank a structure the panel above "
                          "it says cannot be ranked"),
            "missing": absent,
        }
    if verdict is None:
        return None, {
            "excluded": "no friction verdict",
            "reason": ("nothing on file estimates what the round trip costs "
                       "for this structure, so it cannot be scored on an "
                       "axis that subtracts friction"),
            "missing": absent + ["friction verdict"],
        }
    if verdict in EXCLUDING_VERDICTS:
        return None, {
            "excluded": verdict,
            "reason": friction.get("reason") or (
                "friction says {}".format(verdict)),
            "missing": absent,
        }
    if absent:
        return None, {
            "excluded": "missing inputs",
            "reason": ("scored on the inputs present would be scoring it as "
                       "though it had the ones it does not: " +
                       ", ".join(absent)),
            "missing": absent,
        }

    # Every value below is known finite: missing_inputs has just cleared
    # the required ones and the two unbounded sentinels are handled by name.
    substituted = []

    premium = max(abs(_number(row["net_cash"])), MIN_ABS_PREMIUM)
    round_trip = _number(friction.get("round_trip"))
    if round_trip is None:
        # The verdict is not "unknown", so friction was estimated; a
        # round trip that is still absent means zero cost was assumed, and
        # that flatters the edge term. Say so on the row.
        round_trip = 0.0
        substituted.append("round trip cost absent, taken as 0.00, which "
                           "makes the edge term flattering")

    edge_after = _number(row["expected_pnl"]) - round_trip
    clamped = max(-1.0, min(1.0, edge_after / premium))
    edge_norm = (clamped + 1.0) / 2.0

    reward_risk = _number(row.get("reward_risk"))
    if is_unbounded(row["max_gain"]):
        # An unbounded gain has no ratio to cap, and scoring it zero for
        # want of a denominator would rank a long call below every spread.
        rr_norm = 1.0
    else:
        if reward_risk is None:
            substituted.append("reward to risk is not defined for this "
                               "structure, so its reward:risk component "
                               "scored 0.00 rather than being estimated")
        rr_norm = min(reward_risk or 0.0, RR_CAP) / RR_CAP

    max_loss = row["max_loss"]
    if is_unbounded(max_loss) or _number(max_loss) == 0.0:
        # No worst case to measure the shortfall against. The premium is
        # the only figure of the right order that is certainly known, and
        # using it is a choice, not a measurement, so it is declared.
        worst = premium
        substituted.append("worst case is {}, so the expected shortfall was "
                           "measured against the premium of {:.2f} "
                           "instead".format(
                               "unbounded" if is_unbounded(max_loss)
                               else "zero", premium))
    else:
        worst = abs(_number(max_loss))
    es_norm = min(abs(_number(row["expected_shortfall"])) /
                  max(worst, 1e-9), 1.0)

    pop_norm = _number(row["pop"])
    weights = SCORE_WEIGHTS
    base = 100.0 * (weights["pop"] * pop_norm
                    + weights["edge"] * edge_norm
                    + weights["rr"] * rr_norm
                    + weights["es"] * (1.0 - es_norm))

    tilt = 0.0
    is_credit = row["trade_type"] == "credit"
    if vol_view == "crush":
        tilt = VRP_TILT if is_credit else -VRP_TILT
    elif vol_view == "expand":
        tilt = -VRP_TILT if is_credit else VRP_TILT

    score = base + tilt
    thin = THIN_MULTIPLIER if verdict == "thin" else 1.0
    # Order matters and is the source's: the tilt is added to the base and
    # the thin multiplier then scales the total, so a thin structure loses
    # a quarter of its tilt as well as a quarter of its measurements.
    score *= thin
    score = max(0.0, min(100.0, score))

    return score, {
        "pop_norm": pop_norm,
        "edge_norm": edge_norm,
        "rr_norm": rr_norm,
        "es_norm": es_norm,
        "edge_after_friction": edge_after,
        "premium": premium,
        "round_trip": round_trip,
        "worst_case": worst,
        "base_score": base,
        "vrp_tilt": tilt,
        "thin_multiplier": thin,
        "vol_view": vol_view,
        "substituted": substituted,
        "weights": dict(weights),
    }


def rank_rows(rows, vol_view="neutral", top=10):
    """(ranked, rejected): the scored rows in order, and the excluded ones.

    Ranked rows carry score, components and a 1-based rank. Rejected rows
    carry an exclusion dict naming the verdict or the absent inputs. Both
    lists are returned because a leaderboard that hides what it dropped is
    reporting a different set of structures than the one it was given.
    """
    ranked, rejected = [], []
    for row in rows:
        score, components = score_row(row, vol_view)
        if score is None:
            rejected.append(dict(row, exclusion=components))
            continue
        ranked.append(dict(row, score=score, components=components,
                           vol_view=vol_view))
    # Structure name breaks the tie, so an identical pair does not change
    # places between two runs over the same artifacts.
    ranked.sort(key=lambda r: (-r["score"], r.get("structure") or ""))
    for position, row in enumerate(ranked[:top], start=1):
        row["rank"] = position
    return ranked[:top], rejected


def row_from_comparison(row):
    """One comparison-artifact row in the shape score_row reads.

    The comparison artifact is flat and names things differently: its
    expected_loss is the expected shortfall, its friction_cost is the round
    trip, and its friction verdict has no reason attached because the
    reason was flattened into excluded_because when the artifact was
    written. Nothing is invented here: a field that is absent stays absent,
    so score_row can report it as absent.
    """
    verdict = row.get("friction_verdict")
    reason = "; ".join(str(r) for r in (row.get("excluded_because") or []))
    return {
        "structure": row.get("strategy"),
        # Carried so this ranking cannot disagree with the ordering beside
        # it. The comparison excludes a structure whose return on risk is
        # undefined, and this module was scoring that same structure at
        # rank 17 through a premium substitution, so one dashboard showed
        # sixteen ranked and seventeen ranked on two panels of one page.
        "rankable": row.get("rankable"),
        "trade_type": row.get("trade_type"),
        "net_cash": row.get("net_cash"),
        "max_gain": row.get("max_gain"),
        "max_loss": row.get("max_loss"),
        "reward_risk": row.get("reward_risk"),
        "pop": row.get("probability_of_profit"),
        "expected_pnl": row.get("expected_pnl"),
        "expected_shortfall": row.get("expected_loss"),
        "friction": {
            "verdict": verdict,
            "round_trip": row.get("friction_cost"),
            "reason": reason or None,
        } if verdict is not None else {},
    }
