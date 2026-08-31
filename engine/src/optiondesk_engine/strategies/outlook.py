"""The five-direction outlook framework.

Copyright (C) 2026 Iman Samizadeh. Licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate written agreement.
Ported from smartsheep.witty.strategies.outlook.

A market does not have three directions but five, anchored on the one
standard deviation expected move to expiry, which is the 68 percent
probability range a broker platform displays:

  +2  strong bullish   settles above the upper 1 SD band
  +1  mild bullish     up, but inside the band
   0  neutral          finishes near spot
  -1  mild bearish     down, but inside the band
  -2  strong bearish   settles below the lower 1 SD band

Three of the five live inside the normal expected range and two are
extreme. Every strategy in the playbook is defined by which of the five it
needs in order to pay. That is the whole point of the framework: a trade is
chosen by the direction it survives, not by the direction it hopes for.
"""

import math
from enum import IntEnum

DAYS_PER_YEAR = 365.0


class Outlook(IntEnum):
    """The five directional views a structure can express.

    Ordered from -2 to +2 so the distance between two views is arithmetic
    rather than a lookup, which is what lets a structure be scored against a
    view instead of matched to one.
    """
    STRONG_BEARISH = -2
    MILD_BEARISH = -1
    NEUTRAL = 0
    MILD_BULLISH = 1
    STRONG_BULLISH = 2

    @property
    def label(self):
        return {
            -2: "strong bearish (-2)",
            -1: "mild bearish (-1)",
            0: "neutral (0)",
            1: "mild bullish (+1)",
            2: "strong bullish (+2)",
        }[int(self)]


def expected_move(spot, iv, days):
    """One standard deviation move to expiry, in price units.

    iv is annualised implied volatility per 1.00, so 0.25 is 25 percent.
    """
    if spot <= 0 or iv <= 0 or days <= 0:
        raise ValueError("spot, iv and days must all be positive")
    return spot * iv * math.sqrt(days / DAYS_PER_YEAR)


def one_sd_band(spot, iv, days):
    """(lower, upper) edges of the 68 percent probability range."""
    move = expected_move(spot, iv, days)
    return spot - move, spot + move


def classify_target(spot, target, iv, days, neutral_fraction=0.25):
    """Map a price target onto one of the five directions.

    neutral_fraction is how much of the expected move around spot still
    counts as going nowhere. With spot 100 and a 7 point expected move the
    default treats 98.25 to 101.75 as neutral.
    """
    move = expected_move(spot, iv, days)
    if target > spot + move:
        return Outlook.STRONG_BULLISH
    if target < spot - move:
        return Outlook.STRONG_BEARISH
    if abs(target - spot) <= neutral_fraction * move:
        return Outlook.NEUTRAL
    return Outlook.MILD_BULLISH if target > spot else Outlook.MILD_BEARISH


def chain_iv(chain, spot=None):
    """At-the-money implied volatility from a split chain, or None.

    Uses the call closest to spot. Returns None when nothing in the chain
    carries a volatility, which is the honest answer: the band, and every
    strategy that positions against it, is then unavailable rather than
    silently built on a guess.
    """
    spot = spot if spot is not None else chain.get("spot")
    calls = chain.get("calls") or []
    if spot is None or not calls:
        return None
    with_iv = [c for c in calls if c.get("iv")]
    if not with_iv:
        return None
    atm = min(with_iv, key=lambda c: abs(float(c.get("strike", 0.0)) - spot))
    return float(atm["iv"])
