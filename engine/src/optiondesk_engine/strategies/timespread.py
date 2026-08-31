"""Structures whose legs expire on different dates.

Copyright (C) 2026 Iman Samizadeh. Licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate written agreement.
Follows the diagonal work in the author's 001-qaunt desk
(smartsheep.witty.strategies.diagonal), reimplemented against this
project's chain contract.

WHY THESE NEED THEIR OWN ENGINE. Every other structure here settles on one
date, so its profit is piecewise linear in the underlying and the whole
risk graph follows from the strikes alone. A calendar does not. When the
near leg expires the far leg is still alive and still worth something, and
what it is worth depends on a volatility nobody knows yet. The payoff is a
curve rather than a set of line segments, and it can only be drawn by
pricing the surviving leg.

THE ASSUMPTION THAT MATTERS, STATED PLAINLY. The far leg is marked at the
implied volatility it carries today. That is the largest source of error in
a calendar and it is not a small one: the trade is a bet on the difference
between two volatilities, and holding the far one fixed assumes away part
of the thing being traded. A calendar that looks profitable here loses
money if the far leg's volatility falls far enough, and this model cannot
see that coming. Every plan carries the assumption in a field.

Time is in calendar days throughout, matching the rest of the engine.
"""

import math

from optiondesk_engine.pricing.black_scholes import (
    DAYS_PER_YEAR,
    DEFAULT_Q,
    DEFAULT_R,
    bs_price,
)

INF = float("inf")
CURVE_POINTS = 320

ASSUMPTION = (
    "The surviving leg is marked at the implied volatility it carries "
    "today. A time spread is a bet on the difference between two "
    "volatilities, so holding one of them fixed assumes away part of the "
    "trade. Read the profit at the near expiry as the shape of the "
    "structure under an unchanged surface, not as a forecast."
)


class TimeLeg:
    """One leg of a structure whose legs expire on different dates.

    kind    "call" or "put"
    side    +1 long, -1 short
    price   entry premium per unit
    strike  strike price
    qty     contracts
    iv      the leg's own implied volatility, held fixed when marking
    days    calendar days to THIS leg's expiry, at entry
    """

    def __init__(self, kind, side, price, strike, qty, iv, days, ref=None):
        if kind not in ("call", "put"):
            raise ValueError(
                "kind must be 'call' or 'put', got {!r}".format(kind))
        if side not in (1, -1):
            raise ValueError("side must be +1 (long) or -1 (short)")
        if iv is None or float(iv) <= 0:
            raise ValueError(
                "a time leg needs a positive implied volatility: it has to "
                "be marked before it expires, and there is nothing to mark "
                "it with")
        if days is None or float(days) <= 0:
            raise ValueError("a time leg needs positive days to expiry")
        self.kind = kind
        self.side = side
        self.price = float(price)
        self.strike = float(strike)
        self.qty = float(qty)
        self.iv = float(iv)
        self.days = float(days)
        self.ref = ref

    def value_at(self, price, at_days, r=DEFAULT_R, q=DEFAULT_Q):
        """What the leg is worth once at_days have passed.

        At or past its own expiry the leg is worth intrinsic value, which
        is what lets the near leg of a calendar settle correctly while the
        far leg keeps its time value.
        """
        remaining = (self.days - at_days) / DAYS_PER_YEAR
        if remaining <= 0:
            if self.kind == "call":
                return max(price - self.strike, 0.0)
            return max(self.strike - price, 0.0)
        return bs_price(price, self.strike, remaining, self.iv, self.kind,
                        r, q)

    def as_dict(self):
        ref = self.ref or {}
        return {
            "kind": self.kind,
            "side": "long" if self.side > 0 else "short",
            "strike": self.strike,
            "price": self.price,
            "qty": self.qty,
            "iv": self.iv,
            "days_to_expiry": self.days,
            "symbol": ref.get("symbol"),
            "bid": ref.get("bid"),
            "ask": ref.get("ask"),
            "open_interest": ref.get("open_interest"),
            "volume": ref.get("volume"),
        }

    def __repr__(self):
        side = "long" if self.side > 0 else "short"
        return "TimeLeg({} {} {:g} @ {:g} x{:g} {:g}d iv {:.1%})".format(
            side, self.kind, self.strike, self.price, self.qty, self.days,
            self.iv)


def net_option_cash(legs):
    """Cash at entry. Positive is a credit, negative a debit."""
    return sum(-leg.side * leg.qty * leg.price for leg in legs)


def pnl_at(legs, price, at_days, r=DEFAULT_R, q=DEFAULT_Q):
    """Profit once at_days have passed, with the underlying at price."""
    return sum(
        leg.side * leg.qty * (leg.value_at(price, at_days, r, q) - leg.price)
        for leg in legs)


def payoff_curve(legs, lo, hi, at_days, points=CURVE_POINTS, r=DEFAULT_R,
                 q=DEFAULT_Q):
    """(prices, profits) at the mark date, with strikes included exactly."""
    if points < 2:
        raise ValueError("points must be >= 2")
    if hi <= lo:
        raise ValueError("hi must be above lo")
    step = (hi - lo) / (points - 1)
    xs = [lo + i * step for i in range(points)]
    for strike in {leg.strike for leg in legs}:
        if lo < strike < hi:
            xs.append(strike)
    xs = sorted(xs)
    return xs, [pnl_at(legs, x, at_days, r, q) for x in xs]


def analyze_at_front(legs, spot, at_days=None, r=DEFAULT_R, q=DEFAULT_Q,
                     span=0.40):
    """Risk graph at the near expiry.

    Found numerically rather than in closed form, because the surviving leg
    makes the profit a curve. The scan runs to span either side of spot,
    which is wide enough to contain the region that matters and is reported
    alongside, so a reader knows the maximum is a maximum over that window
    rather than over all prices.
    """
    if not legs:
        raise ValueError("no legs")
    if at_days is None:
        at_days = min(leg.days for leg in legs)

    lo = max(spot * (1.0 - span), 0.01)
    hi = spot * (1.0 + span)
    prices, profits = payoff_curve(legs, lo, hi, at_days, CURVE_POINTS, r, q)

    best_index = max(range(len(profits)), key=lambda i: profits[i])
    worst_index = min(range(len(profits)), key=lambda i: profits[i])

    breakevens = []
    for (x0, y0), (x1, y1) in zip(zip(prices, profits),
                                  zip(prices[1:], profits[1:])):
        if y0 == 0.0:
            breakevens.append(x0)
        elif (y0 < 0 < y1) or (y1 < 0 < y0):
            breakevens.append(x0 - y0 * (x1 - x0) / (y1 - y0))
    breakevens = sorted({round(value, 4) for value in breakevens})

    net_cash = net_option_cash(legs)
    max_gain = profits[best_index]
    max_loss = profits[worst_index]
    return {
        "net_cash": net_cash,
        "trade_type": "credit" if net_cash > 0 else "debit",
        "breakevens": breakevens,
        "max_gain": max_gain,
        "max_loss": max_loss,
        "max_gain_at": prices[best_index],
        "max_loss_at": prices[worst_index],
        "reward_risk": (max_gain / abs(max_loss)
                        if max_loss < 0 and max_gain > 0 else None),
        # How much of the peak profit the structure hands back at the far
        # end of the scan. A diagonal can be "too right": past the short
        # strike the long's time value drains against the short's
        # intrinsic and the position gives profit back. Reported so the
        # 1x1 and the ratio can be compared on the number that separates
        # them rather than on the story about them.
        "upside_giveback": max_gain - profits[-1],
        "downside_giveback": max_gain - profits[0],
        "at_days": at_days,
        "scan_range": [lo, hi],
        "scanned_fraction": span,
        "note": ("Maximum gain and loss are over the scanned range, not "
                 "over all prices, because the surviving leg makes the "
                 "profit a curve with no closed form. " + ASSUMPTION),
    }


# --------------------------------------------------------------- builders

def _priced(contracts):
    """Contracts with both a usable price and a volatility to mark with."""
    out = []
    for contract in contracts:
        mid = contract.get("mid")
        if mid is None:
            bid, ask = contract.get("bid"), contract.get("ask")
            if bid is None or ask is None:
                continue
            mid = (float(bid) + float(ask)) / 2.0
        if float(mid) <= 0 or not contract.get("iv"):
            continue
        out.append(dict(contract, mid=float(mid)))
    return out


def _shared_strikes(near, far, kind):
    """Strikes that both chains quote with a usable price and volatility.

    A time spread needs one leg in each expiry, so a strike listed in only
    one of them is no use however close to spot it sits.
    """
    def priced_strikes(chain):
        return {float(c["strike"])
                for c in _priced(_side(chain, kind))
                if c.get("type") == kind}

    return sorted(priced_strikes(near) & priced_strikes(far))


def _closest(contracts, kind, target):
    candidates = [c for c in _priced(contracts) if c.get("type") == kind]
    if not candidates:
        return None
    return min(candidates, key=lambda c: abs(float(c["strike"]) - target))


def _check_order(near, far):
    near_days = near.get("days")
    far_days = far.get("days")
    if not near_days or not far_days:
        raise ValueError("both chains need days to expiry")
    if float(far_days) <= float(near_days):
        raise ValueError(
            "the far expiry must be later than the near one: got {} and {} "
            "days. The chains are the wrong way round.".format(
                near_days, far_days))
    return float(near_days), float(far_days)


def _side(chain, kind):
    return chain["calls"] if kind == "call" else chain["puts"]


def calendar_spread(near, far, kind="call", size=1.0, strike=None):
    """Sell the near expiry and buy the far one at the same strike.

    The structure collects the difference in decay, since the near leg
    loses time value faster than the far one. It wants the underlying to
    sit still and the far leg's volatility to hold up, and a large move in
    either direction hurts it.
    """
    near_days, far_days = _check_order(near, far)
    spot = float(near["spot"])
    target = float(strike) if strike is not None else spot

    # The strike has to be chosen from the strikes both chains price, not
    # from the near chain alone. Real expiries are not listed on the same
    # ladder: a weekly quotes one point apart while a quarterly quotes
    # five, so picking the nearest near-chain strike to spot lands on 766
    # when the far chain lists 760, 765, 770. The old code then took the
    # closest far strike, found 765, saw 766 was not 765, and reported "the
    # strikes or quotes did not admit one" while 765 sat one point from
    # spot in both chains. It made calendars unbuildable on most real
    # pairs, which is not a data problem and was reported as one.
    shared = _shared_strikes(near, far, kind)
    if not shared:
        return None
    chosen = min(shared, key=lambda value: abs(value - target))

    short = _closest(_side(near, kind), kind, chosen)
    long_leg = _closest(_side(far, kind), kind, chosen)
    if short is None or long_leg is None:
        return None
    if abs(float(long_leg["strike"]) - float(short["strike"])) > 1e-9:
        # A calendar is defined by a shared strike. Reaching here means the
        # intersection above disagreed with what _closest returned, which
        # would be a bug rather than a thin chain, and building anyway
        # would misdescribe the structure's risk as a calendar's.
        return None

    legs = [
        TimeLeg(kind, -1, short["mid"], float(short["strike"]), size,
                float(short["iv"]), near_days, ref=short),
        TimeLeg(kind, +1, long_leg["mid"], float(long_leg["strike"]), size,
                float(long_leg["iv"]), far_days, ref=long_leg),
    ]
    return _plan("calendar_spread", legs, spot, near, far, kind)


def diagonal_spread(near, far, kind="call", size=1.0, offset=0.03):
    """A calendar with different strikes: carry plus a directional lean.

    The near leg is sold out of the money by offset, so the structure keeps
    the calendar's decay advantage and gains if the underlying drifts
    toward the short strike.
    """
    near_days, far_days = _check_order(near, far)
    spot = float(near["spot"])
    direction = 1.0 if kind == "call" else -1.0
    short_target = spot * (1.0 + direction * offset)

    short = _closest(_side(near, kind), kind, short_target)
    long_leg = _closest(_side(far, kind), kind, spot)
    if short is None or long_leg is None:
        return None
    # The short strike has to sit beyond the long one in the direction of
    # the lean, or the structure is not a diagonal.
    if kind == "call" and float(short["strike"]) <= float(long_leg["strike"]):
        return None
    if kind == "put" and float(short["strike"]) >= float(long_leg["strike"]):
        return None

    legs = [
        TimeLeg(kind, -1, short["mid"], float(short["strike"]), size,
                float(short["iv"]), near_days, ref=short),
        TimeLeg(kind, +1, long_leg["mid"], float(long_leg["strike"]), size,
                float(long_leg["iv"]), far_days, ref=long_leg),
    ]
    return _plan("diagonal_spread", legs, spot, near, far, kind)


def _delta_of(contract, spot, kind, r=DEFAULT_R, q=DEFAULT_Q):
    """The contract's delta, computed when the chain does not carry one.

    A chain snapshot in this project holds prices and volatilities, not
    Greeks: the ladder is a separate artifact. The delta-targeted leg
    selection these structures need therefore has to derive it, from the
    contract's own implied volatility, rather than read it.
    """
    if contract.get("delta") is not None:
        return abs(float(contract["delta"]))
    iv = contract.get("iv")
    days = contract.get("days") or contract.get("days_to_expiry")
    if not iv or not days:
        return None
    t = float(days) / DAYS_PER_YEAR
    if t <= 0:
        return None
    strike = float(contract["strike"])
    d1 = ((math.log(spot / strike) + (r - q + 0.5 * float(iv) ** 2) * t)
          / (float(iv) * math.sqrt(t)))
    cdf = 0.5 * (1.0 + math.erf(d1 / math.sqrt(2.0)))
    delta = math.exp(-q * t) * (cdf if kind == "call" else cdf - 1.0)
    return abs(delta)


def _by_delta(contracts, kind, target, spot, days):
    """The priced contract whose absolute delta is nearest the target."""
    scored = []
    for contract in _priced(contracts):
        if contract.get("type") != kind:
            continue
        enriched = dict(contract)
        enriched.setdefault("days", days)
        delta = _delta_of(enriched, spot, kind)
        if delta is None:
            continue
        scored.append((abs(delta - target), enriched, delta))
    if not scored:
        return None, None
    _, contract, delta = min(scored, key=lambda row: row[0])
    return contract, delta


def _ratio_diagonal(near, far, kind, size=1.0, long_delta=0.65,
                    short_delta=0.25, long_qty=2.0, short_qty=1.0):
    """Back-month longs against fewer front-month shorts, at a delta ratio.

    Ported from the author's 001-qaunt work
    (smartsheep.witty.strategies.diagonal.ratio_call_diagonal), which
    built it from the Smolinsky study: the workhorse expression for a
    leader breaking out is a long back-month contract at 50 to 80 delta
    with nearer contracts sold against it at a ratio, so the front shorts
    subsidise the carry without capping the move.

    The constraint that makes it that trade rather than a 1x1 with extra
    contracts is enforced here rather than assumed: the short delta mass
    must stay strictly below the long delta mass. When it does not, the
    structure caps the very move it was opened for, and this returns
    nothing instead of a plan that would misdescribe itself.

    Legs are chosen by delta, not by distance from spot. A 65 delta back
    month leg is in the money on purpose.
    """
    near_days, far_days = _check_order(near, far)
    spot = float(near["spot"])

    long_opt, long_d = _by_delta(_side(far, kind), kind, long_delta, spot,
                                 far_days)
    short_opt, short_d = _by_delta(_side(near, kind), kind, short_delta,
                                   spot, near_days)
    if long_opt is None or short_opt is None:
        return None

    # The short has to be the further out of the money contract of the
    # pair, or this is not a diagonal in the intended direction.
    if kind == "call" and float(short_opt["strike"]) <= float(
            long_opt["strike"]):
        return None
    if kind == "put" and float(short_opt["strike"]) >= float(
            long_opt["strike"]):
        return None

    long_mass = long_d * long_qty * size
    short_mass = short_d * short_qty * size
    if short_mass >= long_mass:
        return None

    legs = [
        TimeLeg(kind, +1, long_opt["mid"], float(long_opt["strike"]),
                long_qty * size, float(long_opt["iv"]), far_days,
                ref=long_opt),
        TimeLeg(kind, -1, short_opt["mid"], float(short_opt["strike"]),
                short_qty * size, float(short_opt["iv"]), near_days,
                ref=short_opt),
    ]
    name = "ratio_{}_diagonal".format(kind)
    plan = _plan(name, legs, spot, near, far, kind)
    analysis = plan["analysis"]
    plan["delta_ratio"] = short_mass / long_mass
    plan["long_delta"] = long_d
    plan["short_delta"] = short_d
    plan["giveback"] = (analysis["upside_giveback"] if kind == "call"
                        else analysis["downside_giveback"])
    return plan


def ratio_call_diagonal(near, far, kind=None, size=1.0, **kwargs):
    """Bullish ratio diagonal. kind is fixed by the name."""
    return _ratio_diagonal(near, far, "call", size=size, **kwargs)


def ratio_put_diagonal(near, far, kind=None, size=1.0, **kwargs):
    """Bearish mirror of the ratio call diagonal."""
    return _ratio_diagonal(near, far, "put", size=size, **kwargs)


BUILDERS = {
    "calendar_spread": calendar_spread,
    "diagonal_spread": diagonal_spread,
    "ratio_call_diagonal": ratio_call_diagonal,
    "ratio_put_diagonal": ratio_put_diagonal,
}


def build_time_spread(name, near, far, **kwargs):
    """Build a two-expiry structure by name."""
    builder = BUILDERS.get(name)
    if builder is None:
        raise KeyError("unknown time spread {!r}. Known: {}".format(
            name, ", ".join(sorted(BUILDERS))))
    return builder(near, far, **kwargs)


def _plan(name, legs, spot, near, far, kind):
    analysis = analyze_at_front(legs, spot)
    return {
        "strategy": name,
        "trade_type": analysis["trade_type"],
        "kind": kind,
        "spot": spot,
        "near_expiry": near.get("expiry"),
        "far_expiry": far.get("expiry"),
        "near_days": min(leg.days for leg in legs),
        "far_days": max(leg.days for leg in legs),
        "legs": legs,
        "analysis": analysis,
        "assumption": ASSUMPTION,
    }
