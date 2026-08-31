"""Friction and liquidity gate for strategy plans.

Copyright (C) 2026 Iman Samizadeh. Licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate written agreement.
Ported from smartsheep.witty.strategies.friction.

A market effect only becomes a profit mechanism if it survives friction.
Plans in this project are priced at snapshot mids, which no live order
achieves. This module estimates what the round trip actually costs at the
quoted spreads and grades the result.

The model is deliberately simple and stated in full, because a friction
number nobody can reconstruct is worse than none:

  half spread   (ask - bid) / 2 per option leg
  entry cost    qty * half_spread * HAIRCUT, where the haircut is the
                fraction of the half spread a patient limit order concedes
  round trip    twice the entry, since opening and closing both concede
  commission    a flat per-contract fee, both ways

Verdicts compare the round trip to the premium at stake:

  ok            friction below OK_MAX of the net premium
  thin          between OK_MAX and THIN_MAX. The edge has to be real to
                survive this; treat any modelled advantage as halved
  untradeable   above THIN_MAX, or a leg quoting wider than
                MAX_REL_SPREAD of its own mid, or a leg with no bid

Depth flags are advisory and never blocking: low open interest or zero
volume tells you the exit may be worse than the entry, not that the trade
is forbidden.

Honesty, stated in code rather than only in a document: these are snapshot
quotes, live spreads move, size is not modelled at all beyond one lot, and
a verdict of ok is not a promise of a fill.
"""

HAIRCUT = 0.5
COMMISSION_PER_CONTRACT = 0.0
OK_MAX = 0.10
THIN_MAX = 0.25
MAX_REL_SPREAD = 0.40
MIN_OPEN_INTEREST = 10


def leg_quote(leg):
    """(bid, ask, mid, open_interest, volume) from a leg's source contract."""
    ref = getattr(leg, "ref", None) or {}
    bid = ref.get("bid")
    ask = ref.get("ask")
    mid = ref.get("mid")
    if mid is None and bid is not None and ask is not None:
        mid = (float(bid) + float(ask)) / 2.0
    return (
        None if bid is None else float(bid),
        None if ask is None else float(ask),
        None if mid is None else float(mid),
        ref.get("open_interest"),
        ref.get("volume"),
    )


def plan_friction(legs, net_cash=None, commission=COMMISSION_PER_CONTRACT,
                  haircut=HAIRCUT):
    """Estimate the round trip cost of trading a plan's legs.

    Underlying legs are ignored: their spread belongs to the underlying
    market and is a different cost with different mechanics.

    Returns round_trip, entry_cost, rel_to_premium, worst_rel_spread,
    legs_without_quotes, depth_flags, verdict and reason. The verdict is
    "unknown" when no option leg carries a two-sided quote, which is a
    different statement from "fine".
    """
    entry = 0.0
    worst_rel = 0.0
    quoted = 0
    missing = 0
    contracts = 0.0
    depth_flags = []
    no_bid = False

    for leg in legs:
        if getattr(leg, "kind", None) == "underlying":
            continue
        bid, ask, mid, open_interest, volume = leg_quote(leg)
        qty = abs(float(getattr(leg, "qty", 1.0)))
        contracts += qty
        if bid is None or ask is None or ask <= 0:
            missing += 1
            continue
        if bid <= 0:
            no_bid = True
        quoted += 1
        half_spread = max((ask - bid) / 2.0, 0.0)
        entry += qty * half_spread * haircut
        if mid and mid > 0:
            worst_rel = max(worst_rel, (ask - bid) / mid)
        if open_interest is not None and int(open_interest) < MIN_OPEN_INTEREST:
            depth_flags.append("strike {} open interest {}".format(
                getattr(leg, "strike", "?"), open_interest))
        if volume is not None and int(volume) == 0:
            depth_flags.append("strike {} traded zero contracts today".format(
                getattr(leg, "strike", "?")))

    round_trip = 2.0 * entry + commission * contracts * 2.0

    if quoted == 0:
        return {
            "round_trip": None,
            "entry_cost": None,
            "rel_to_premium": None,
            "worst_rel_spread": None,
            "legs_without_quotes": missing,
            "depth_flags": depth_flags,
            "verdict": "unknown",
            "reason": "no option leg carries a two-sided quote, so friction "
                      "cannot be estimated",
        }

    premium = abs(float(net_cash)) if net_cash else 0.0
    rel = round_trip / premium if premium > 0 else None

    if no_bid:
        verdict = "untradeable"
        reason = "a leg has no bid, so there is no exit at any price"
    elif worst_rel > MAX_REL_SPREAD:
        verdict = "untradeable"
        reason = ("widest leg quotes {:.0f} percent of its own mid, above "
                  "the {:.0f} percent limit".format(worst_rel * 100,
                                                    MAX_REL_SPREAD * 100))
    elif rel is None:
        verdict = "unknown"
        reason = "no net premium to compare the round trip against"
    elif rel <= OK_MAX:
        verdict = "ok"
        reason = "round trip is {:.1f} percent of the premium".format(rel * 100)
    elif rel <= THIN_MAX:
        verdict = "thin"
        reason = ("round trip is {:.1f} percent of the premium; the edge "
                  "must be strong to survive it".format(rel * 100))
    else:
        verdict = "untradeable"
        reason = ("round trip is {:.1f} percent of the premium, above the "
                  "{:.0f} percent limit".format(rel * 100, THIN_MAX * 100))

    return {
        "round_trip": round_trip,
        "entry_cost": entry,
        "rel_to_premium": rel,
        "worst_rel_spread": worst_rel,
        "legs_without_quotes": missing,
        "depth_flags": depth_flags,
        "verdict": verdict,
        "reason": reason,
    }
