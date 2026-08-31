"""Volatility smile geometry: the numbers a volatility trader quotes.

Copyright (C) 2026 Iman Samizadeh. Licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate written agreement.

A chain has hundreds of contracts and a trader carries four numbers from it:
where at-the-money volatility sits, how much more the downside costs than
the upside, how convex the wings are, and what the market implies the range
to be. This module computes those from a graded ladder.

Definitions, stated because the market uses the same words for different
conventions:

  atm_iv        volatility of the contract whose strike is nearest spot.
                Not an interpolated forward-at-the-money volatility; the
                difference is small for liquid chains and material for
                wide ones, so the strike used is reported alongside.
  risk_reversal 25-delta put volatility minus 25-delta call volatility.
                Positive means the downside is bid, which is the normal
                state for equity indices. This is the sign convention
                where a bigger number means more fear.
  butterfly     average of the two 25-delta wings minus at-the-money,
                a measure of how convex the smile is.
  skew_slope    change in volatility per one percent change in strike,
                fitted by least squares across the graded band. A single
                number for "how tilted is this smile".

Deltas come from the ladder rows, which carry the engine's own Greeks, so
the 25-delta strikes are the ones the model actually implies rather than a
rule of thumb about moneyness.
"""

TARGET_DELTA = 0.25

# How far from the target delta a contract may sit and still be called a
# wing. Without this the nearest contract was always accepted, so a chain
# whose most extreme delta was 0.45 still reported a 25-delta risk
# reversal, computed from strikes one point either side of spot.
DELTA_TOLERANCE = 0.10


def _nearest_by_delta(rows, kind, target, tolerance=DELTA_TOLERANCE):
    """The contract nearest the target delta, or None if none is near.

    Returning the nearest contract unconditionally is how a chain that
    never reaches the target still produces a number labelled with it.
    """
    candidates = [r for r in rows
                  if r.get("type") == kind and r.get("delta") is not None
                  and r.get("iv")]
    if not candidates:
        return None
    best = min(candidates,
               key=lambda r: abs(abs(float(r["delta"])) - target))
    if abs(abs(float(best["delta"])) - target) > tolerance:
        return None
    return best


def _least_squares_slope(points):
    """Ordinary least squares slope through (x, y) pairs."""
    if len(points) < 3:
        return None
    n = float(len(points))
    mean_x = sum(x for x, _ in points) / n
    mean_y = sum(y for _, y in points) / n
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in points)
    denominator = sum((x - mean_x) ** 2 for x, _ in points)
    if denominator == 0:
        return None
    return numerator / denominator


def smile_metrics(rows, spot, days=None, target_delta=TARGET_DELTA):
    """Smile geometry from graded ladder rows, or None where unavailable.

    Every field can be None independently. A chain that does not reach a
    25-delta put simply has no risk reversal, and saying so is better than
    extrapolating one from the strikes that do exist.
    """
    graded = [r for r in rows if r.get("iv")]
    if not graded or not spot or spot <= 0:
        return None

    # Ties between a call and a put at the same strike were broken by
    # whichever appeared first in the list, which swung the headline
    # expected move by 50 percent on the same chain. Calls win the tie,
    # deterministically, and the type used is reported.
    atm = min(graded, key=lambda r: (abs(float(r["strike"]) - spot),
                                     0 if r.get("type") == "call" else 1))
    atm_iv = float(atm["iv"])

    call_wing = _nearest_by_delta(graded, "call", target_delta)
    put_wing = _nearest_by_delta(graded, "put", target_delta)

    risk_reversal = butterfly = None
    if call_wing and put_wing:
        risk_reversal = float(put_wing["iv"]) - float(call_wing["iv"])
        butterfly = ((float(put_wing["iv"]) + float(call_wing["iv"])) / 2.0
                     - atm_iv)

    # Slope is fitted on calls only: mixing both sides double counts every
    # strike and flattens the fit toward zero.
    call_points = [((float(r["strike"]) / spot - 1.0) * 100.0, float(r["iv"]))
                   for r in graded if r.get("type") == "call"]
    slope = _least_squares_slope(sorted(call_points))

    expected_move = None
    if days and days > 0:
        expected_move = spot * atm_iv * (days / 365.0) ** 0.5

    return {
        "atm_iv": atm_iv,
        "atm_strike": float(atm["strike"]),
        "atm_type": atm.get("type"),
        "spot": spot,
        "risk_reversal": risk_reversal,
        "butterfly": butterfly,
        "skew_slope_per_percent": slope,
        "call_wing": ({"strike": float(call_wing["strike"]),
                       "delta": float(call_wing["delta"]),
                       "iv": float(call_wing["iv"])} if call_wing else None),
        "put_wing": ({"strike": float(put_wing["strike"]),
                      "delta": float(put_wing["delta"]),
                      "iv": float(put_wing["iv"])} if put_wing else None),
        "expected_move": expected_move,
        # An arithmetic band on a lognormal can reach below zero at high
        # volatility, and a negative price is not a bound anyone can use.
        "expected_range": ([max(spot - expected_move, 0.0),
                            spot + expected_move]
                           if expected_move else None),
        "expected_range_floored": bool(expected_move
                                       and spot - expected_move < 0),
        "graded_contracts": len(graded),
        "target_delta": target_delta,
        "convention": (
            "wings must sit within {} of the target delta or they are "
            "reported as absent rather than substituted. ".format(
                DELTA_TOLERANCE)
            + "risk reversal is 25-delta put volatility minus 25-delta call "
            "volatility, so a positive number means the downside is bid. "
            "Butterfly is the average wing minus at-the-money. At-the-money "
            "is the nearest listed strike, not an interpolated forward."),
    }
