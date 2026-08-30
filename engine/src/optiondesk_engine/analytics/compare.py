"""Rank structures against each other under a stated, visible criterion.

Copyright (C) 2026 Iman Samizadeh. Licensed under AGPL-3.0-only.

WHAT THIS IS. Given several plans built from the same chain, it puts them in
one table and orders them by expected profit per unit of capital at risk,
under the same lognormal model that produced their probabilities. Every
component of the score is returned, so the order can be argued with rather
than merely accepted.

WHAT THIS IS NOT, and the caveat matters more than the ranking. The expected
values come from a model, and the model disagrees with the market in a
specific way: it prices every strike from one at-the-money volatility, while
the market prices each strike with its own. That disagreement is the smile.
Any structure that looks profitable in expectation is, to a first
approximation, one that sells strikes where the market's volatility exceeds
the single number the model used. That is a measurement of the smile, not a
discovered edge, and it disappears the moment the model prices each strike
at the volatility the market actually quotes.

Two more reasons the top row is not a recommendation: mid-quote premiums are
not fills, and the friction estimate is the only part of this that touches
the cost of trading. A structure is excluded from the ranking outright when
friction says it is untradeable, because a positive expectation that cannot
be entered is not an opportunity.
"""

import math

CAVEAT = (
    "Ranked by model expected profit per unit of capital at risk, under a "
    "lognormal settlement model at a single at-the-money volatility. The "
    "market prices each strike with its own volatility, so a positive "
    "expectation here largely measures that disagreement rather than an "
    "edge. Premiums are mid quotes, not fills. This is an ordering of "
    "structures under stated assumptions, not a recommendation to trade "
    "any of them."
)

UNBOUNDED = "unlimited"


def _risk_capital(plan):
    """Capital genuinely at risk, or None when the loss is unbounded.

    A structure with unbounded loss has no denominator, so it cannot be
    ranked on return per unit of risk and is reported separately rather
    than being given a flattering finite number.
    """
    analysis = plan.get("analysis") or {}
    max_loss = analysis.get("max_loss")
    if max_loss is None or isinstance(max_loss, str):
        return None
    try:
        loss = float(max_loss)
    except (TypeError, ValueError):
        return None
    # The engine returns float("-inf") for an unbounded loss; the shell
    # serialises that to the string "unlimited". Checking only the string
    # let an infinity through as a capital-at-risk of inf, which produced a
    # return on risk of exactly 0.0 and ranked a naked short call above a
    # defined-risk structure.
    if not math.isfinite(loss):
        return None
    # A worst case that is a profit is not capital at risk.
    if loss >= 0:
        return None
    loss = abs(loss)
    return loss if loss > 1e-9 else None


def score_plan(plan):
    """Score components for one plan. Every field can be None."""
    analysis = plan.get("analysis") or {}
    probability = plan.get("probability") or {}
    friction = plan.get("friction") or {}
    greeks = plan.get("net_greeks") or {}

    risk = _risk_capital(plan)
    expected = probability.get("expected_pnl")
    expected_return = (expected / risk
                       if expected is not None and risk else None)

    reasons = []
    tradeable = friction.get("verdict") not in ("untradeable",)
    if not tradeable:
        reasons.append("friction says untradeable: " +
                       str(friction.get("reason", "")))
    if risk is None:
        max_loss = analysis.get("max_loss")
        if isinstance(max_loss, str) or (
                isinstance(max_loss, (int, float))
                and not math.isfinite(float(max_loss))):
            reasons.append("loss is unbounded, so return on risk is "
                           "undefined")
        elif isinstance(max_loss, (int, float)) and float(max_loss) >= 0:
            reasons.append("the worst outcome is a profit, so there is no "
                           "capital at risk to divide by")
        else:
            reasons.append("no capital at risk could be established")
    if expected is None:
        reasons.append("no model expectation available")
    elif not math.isfinite(float(expected)):
        reasons.append("the model expectation is not a finite number")
    if (plan.get("meta") or {}).get("degraded"):
        reasons.append("built from a degraded snapshot")

    finite_expectation = (expected is not None
                          and math.isfinite(float(expected)))
    return {
        "strategy": plan.get("strategy"),
        "trade_type": analysis.get("trade_type"),
        "net_cash": analysis.get("net_cash"),
        "max_gain": analysis.get("max_gain"),
        "max_loss": analysis.get("max_loss"),
        "capital_at_risk": risk,
        "reward_risk": analysis.get("reward_risk"),
        "breakevens": analysis.get("breakevens"),
        "probability_of_profit": probability.get("profit"),
        "probability_of_loss": probability.get("loss"),
        "expected_pnl": expected,
        "expected_loss": probability.get("expected_loss"),
        "expected_return_on_risk": expected_return,
        "net_delta": greeks.get("delta"),
        "net_theta": greeks.get("theta"),
        "net_vega": greeks.get("vega"),
        "net_gamma": greeks.get("gamma"),
        "friction_verdict": friction.get("verdict"),
        "friction_cost": friction.get("round_trip"),
        "rankable": bool(tradeable and risk and finite_expectation
                         and expected_return is not None
                         and math.isfinite(expected_return)),
        "excluded_because": reasons,
    }


def rank_strategies(plans):
    """Compare plans and order the rankable ones, best first.

    Returns the full table, the ordered subset, the leader, and the caveat
    that must travel with any of it. The leader is None when nothing is
    rankable, which is a real outcome and not an error.
    """
    rows = [score_plan(plan) for plan in plans]
    rankable = [row for row in rows if row["rankable"]]
    rankable.sort(key=lambda r: (-(r["expected_return_on_risk"] or 0.0),
                                 -(r["probability_of_profit"] or 0.0),
                                 r["strategy"] or ""))
    for position, row in enumerate(rankable, start=1):
        row["rank"] = position

    leader = rankable[0] if rankable else None
    margin = None
    if len(rankable) > 1:
        first = rankable[0]["expected_return_on_risk"]
        second = rankable[1]["expected_return_on_risk"]
        margin = first - second

    return {
        "rows": rows,
        "ranked": rankable,
        "leader": leader,
        "margin_over_runner_up": margin,
        "rankable_count": len(rankable),
        "excluded_count": len(rows) - len(rankable),
        "criterion": ("model expected profit divided by capital at risk, "
                      "ties broken by model probability of profit"),
        "caveat": CAVEAT,
    }
