"""Strategy constructors and the playbook registry.

Copyright (C) 2026 Iman Samizadeh. Licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate written agreement.
Ported from smartsheep.witty.strategies.playbook and adapted to the chain
snapshot contract used by this project.

Each constructor takes a chain and returns a plan:

    strategy      name
    trade_type    debit (money out) or credit (money in)
    outlooks      which of the five directions the trade profits from
    when_to_use   the guidance that goes with it
    legs          a list of payoff.Leg
    analysis      breakevens, max gain, max loss, reward to risk, net cash

The registry PLAYBOOK is the strategy table as data, so recommend() can
rank strategies for a view without any of them being special-cased.

Strategies needing two expiries (calendars and diagonals) are present in
the registry with build set to None. They are declared rather than
silently omitted, so the gap is visible and the recommendation engine can
still mention them.
"""

from optiondesk_engine.strategies.outlook import (
    Outlook,
    chain_iv,
    one_sd_band,
)
from optiondesk_engine.strategies.payoff import (
    INF,
    Leg,
    analyze,
    pnl_at_expiry,
)


# --------------------------------------------------------------- chain shape

def split_chain(snapshot, spot=None):
    """Normalise a chain snapshot into {'calls', 'puts', 'spot', 'days'}.

    Accepts this project's snapshot (a flat contracts list carrying a type
    field) and the older calls/puts shape, so the same builders work on
    both. Contracts with no usable implied volatility are kept: a strategy
    can still be priced from quotes, and the volatility only matters for
    the expected move band, which reports itself unavailable instead.
    """
    if "contracts" in snapshot:
        contracts = snapshot["contracts"]
        calls = [c for c in contracts if c.get("type") == "call"]
        puts = [c for c in contracts if c.get("type") == "put"]
    else:
        calls = list(snapshot.get("calls") or [])
        puts = list(snapshot.get("puts") or [])
    calls.sort(key=lambda c: float(c["strike"]))
    puts.sort(key=lambda c: float(c["strike"]))
    resolved_spot = spot if spot is not None else snapshot.get("spot")
    if resolved_spot is None:
        raise ValueError("spot price required: pass spot= or set it on the "
                         "snapshot")
    return {
        "calls": calls,
        "puts": puts,
        "spot": float(resolved_spot),
        "days": snapshot.get("days_to_expiry"),
        "expiry": snapshot.get("expiry"),
    }


def _strike(option):
    return float(option["strike"])


def _mid(option):
    """Usable price for a contract, or a refusal.

    A leg priced from a stale last trade instead of a live two-sided quote
    is how a plan ends up with a breakeven nobody could achieve, so a
    contract with no mid and no both-sided quote is rejected outright.
    """
    if option.get("mid") is not None:
        return float(option["mid"])
    bid, ask = option.get("bid"), option.get("ask")
    if bid is not None and ask is not None and (bid or ask):
        return (float(bid) + float(ask)) / 2.0
    raise ValueError("contract {} has no usable price".format(
        option.get("symbol", option.get("strike"))))


def _priced(options):
    """Only the contracts that can actually be priced."""
    out = []
    for option in options:
        try:
            _mid(option)
        except (ValueError, TypeError):
            continue
        out.append(option)
    return out


def _closest(options, price):
    usable = _priced(options)
    if not usable:
        raise ValueError("no priced contracts to choose from")
    return min(usable, key=lambda o: abs(_strike(o) - price))


def _band(chain, iv=None, days=None):
    """The one standard deviation band, or None when it cannot be built."""
    iv = iv if iv is not None else chain_iv(chain, chain["spot"])
    days = days if days is not None else chain.get("days")
    if not iv or not days or days <= 0:
        return None
    return one_sd_band(chain["spot"], iv, days)


def _plan(name, legs, chain, band=None):
    meta = PLAYBOOK[name]
    return {
        "strategy": name,
        "trade_type": meta["trade_type"],
        "outlooks": [int(o) for o in meta["outlooks"]],
        "outlook_labels": [o.label for o in meta["outlooks"]],
        "when_to_use": meta["when_to_use"],
        "spot": chain["spot"],
        "expiry": chain.get("expiry"),
        "days_to_expiry": chain.get("days"),
        "band": list(band) if band else None,
        "legs": legs,
        "analysis": analyze(legs, spot=chain["spot"]),
    }


# ------------------------------------------------------- debit directional

def long_call(chain, iv=None, days=None, size=1.0):
    """Stock replacement. Uncapped upside, risk capped at the premium."""
    option = _closest(chain["calls"], chain["spot"])
    legs = [Leg("call", +1, _mid(option), strike=_strike(option), qty=size,
                ref=option)]
    return _plan("long_call", legs, chain, _band(chain, iv, days))


def long_put(chain, iv=None, days=None, size=1.0):
    """Alternative to shorting. Bearish, risk capped at the premium."""
    option = _closest(chain["puts"], chain["spot"])
    legs = [Leg("put", +1, _mid(option), strike=_strike(option), qty=size,
                ref=option)]
    return _plan("long_put", legs, chain, _band(chain, iv, days))


def bull_call_spread(chain, iv=None, days=None, size=1.0,
                     min_reward_risk=1.0):
    """Buy the lower strike call, sell a higher one against it.

    The short strike is kept inside the one standard deviation band, so
    the trade reaches maximum profit on a normal move rather than needing
    an extreme one. That is the whole reason a spread beats a naked long
    call for most views.
    """
    spot = chain["spot"]
    band = _band(chain, iv, days)
    calls = _priced(chain["calls"])
    best, best_score = None, -INF
    near_money = sorted((c for c in calls if _strike(c) <= spot * 1.01),
                        key=lambda c: abs(_strike(c) - spot))[:3]
    for long_opt in near_money:
        for short_opt in calls:
            if _strike(short_opt) <= _strike(long_opt):
                continue
            if band and _strike(short_opt) > band[1]:
                continue
            legs = [
                Leg("call", +1, _mid(long_opt), strike=_strike(long_opt),
                    qty=size, ref=long_opt),
                Leg("call", -1, _mid(short_opt), strike=_strike(short_opt),
                    qty=size, ref=short_opt),
            ]
            metrics = analyze(legs, spot=spot)
            if metrics["net_cash"] >= 0 or not metrics["reward_risk"]:
                continue
            if metrics["reward_risk"] < min_reward_risk:
                continue
            score = metrics["reward_risk"]
            score -= (metrics["breakevens"][0] - spot) / spot * 5
            if score > best_score:
                best, best_score = _plan("bull_call_spread", legs, chain,
                                         band), score
    return best


def bear_put_spread(chain, iv=None, days=None, size=1.0,
                    min_reward_risk=1.0):
    """Mirror of the bull call spread: buy the higher put, sell a lower."""
    spot = chain["spot"]
    band = _band(chain, iv, days)
    puts = _priced(chain["puts"])
    best, best_score = None, -INF
    near_money = sorted((p for p in puts if _strike(p) >= spot * 0.99),
                        key=lambda p: abs(_strike(p) - spot))[:3]
    for long_opt in near_money:
        for short_opt in puts:
            if _strike(short_opt) >= _strike(long_opt):
                continue
            if band and _strike(short_opt) < band[0]:
                continue
            legs = [
                Leg("put", +1, _mid(long_opt), strike=_strike(long_opt),
                    qty=size, ref=long_opt),
                Leg("put", -1, _mid(short_opt), strike=_strike(short_opt),
                    qty=size, ref=short_opt),
            ]
            metrics = analyze(legs, spot=spot)
            if metrics["net_cash"] >= 0 or not metrics["reward_risk"]:
                continue
            if metrics["reward_risk"] < min_reward_risk:
                continue
            score = metrics["reward_risk"]
            score -= (spot - metrics["breakevens"][-1]) / spot * 5
            if score > best_score:
                best, best_score = _plan("bear_put_spread", legs, chain,
                                         band), score
    return best


# ------------------------------------------------------------ credit income

def cash_secured_put(chain, iv=None, days=None, size=1.0):
    """Sell a put below the lower band edge.

    Pays in four of the five directions; only the extreme drop hurts. Size
    it as though assignment were certain, because the day it matters, it
    is.
    """
    spot = chain["spot"]
    band = _band(chain, iv, days)
    puts = _priced(chain["puts"])
    if band:
        candidates = [p for p in puts if _strike(p) <= band[0]]
    else:
        candidates = [p for p in puts if _strike(p) <= spot * 0.95]
    if not candidates:
        return None
    option = max(candidates, key=_strike)
    legs = [Leg("put", -1, _mid(option), strike=_strike(option), qty=size,
                ref=option)]
    return _plan("cash_secured_put", legs, chain, band)


def covered_call(chain, iv=None, days=None, size=1.0, underlying_entry=None):
    """Own the underlying and sell a call above the upper band edge."""
    spot = chain["spot"]
    entry = float(underlying_entry) if underlying_entry is not None else spot
    band = _band(chain, iv, days)
    calls = _priced(chain["calls"])
    if band:
        candidates = [c for c in calls if _strike(c) >= band[1]]
    else:
        candidates = [c for c in calls if _strike(c) >= spot * 1.05]
    if not candidates:
        return None
    option = min(candidates, key=_strike)
    legs = [
        Leg("underlying", +1, entry, qty=size),
        Leg("call", -1, _mid(option), strike=_strike(option), qty=size,
            ref=option),
    ]
    return _plan("covered_call", legs, chain, band)


def protective_put(chain, iv=None, days=None, size=1.0,
                   underlying_entry=None):
    """Long underlying plus a long at-the-money put. Insurance."""
    spot = chain["spot"]
    entry = float(underlying_entry) if underlying_entry is not None else spot
    option = _closest(chain["puts"], spot)
    legs = [
        Leg("underlying", +1, entry, qty=size),
        Leg("put", +1, _mid(option), strike=_strike(option), qty=size,
            ref=option),
    ]
    return _plan("protective_put", legs, chain, _band(chain, iv, days))


# ------------------------------------------------------------- volatility

def straddle(chain, iv=None, days=None, size=1.0):
    """Buy the at-the-money call and put. A storm, direction unknown."""
    call_opt = _closest(chain["calls"], chain["spot"])
    put_opt = _closest(chain["puts"], _strike(call_opt))
    legs = [
        Leg("call", +1, _mid(call_opt), strike=_strike(call_opt), qty=size,
            ref=call_opt),
        Leg("put", +1, _mid(put_opt), strike=_strike(put_opt), qty=size,
            ref=put_opt),
    ]
    return _plan("straddle", legs, chain, _band(chain, iv, days))


def strangle(chain, iv=None, days=None, size=1.0, wing_fraction=0.5):
    """The cheaper cousin: an out of the money call and put.

    Less to lose, but the move has to be bigger. Wings default to half the
    expected move either side of spot.
    """
    spot = chain["spot"]
    band = _band(chain, iv, days)
    offset = (band[1] - spot) * wing_fraction if band else spot * 0.03
    call_opt = _closest(chain["calls"], spot + offset)
    put_opt = _closest(chain["puts"], spot - offset)
    if _strike(call_opt) <= _strike(put_opt):
        return straddle(chain, iv, days, size)
    legs = [
        Leg("call", +1, _mid(call_opt), strike=_strike(call_opt), qty=size,
            ref=call_opt),
        Leg("put", +1, _mid(put_opt), strike=_strike(put_opt), qty=size,
            ref=put_opt),
    ]
    return _plan("strangle", legs, chain, band)


def bull_put_spread(chain, iv=None, days=None, size=1.0,
                    wing_width_fraction=0.5):
    """Sell a put at the lower band edge, buy a lower one to cap the loss.

    The credit half of a bullish view. Where a bull call spread pays a
    debit and needs the move to happen, this collects the premium and
    needs the move not to happen against it. Both are bullish and they
    are not the same trade, which is why the old spread algo enumerated
    the debit and credit verticals as separate families.

    Ported from the credit vertical enumeration in the author's 001-qaunt
    spread engine (smartsheep.witty.strategies.spreads.spread_engine).
    """
    spot = chain["spot"]
    band = _band(chain, iv, days)
    reference = band or (spot * 0.95, spot * 1.05)
    width = (reference[1] - reference[0]) * wing_width_fraction / 2.0

    short_opt = _closest(chain["puts"], reference[0])
    long_opt = _closest(chain["puts"], _strike(short_opt) - width)
    if _strike(long_opt) >= _strike(short_opt):
        return None
    legs = [
        Leg("put", -1, _mid(short_opt), strike=_strike(short_opt), qty=size,
            ref=short_opt),
        Leg("put", +1, _mid(long_opt), strike=_strike(long_opt), qty=size,
            ref=long_opt),
    ]
    plan = _plan("bull_put_spread", legs, chain, band)
    # A credit spread that pays a debit has its strikes the wrong way
    # round or its quotes crossed. Either way it is not this structure.
    if plan["analysis"]["net_cash"] <= 0:
        return None
    return plan


def bear_call_spread(chain, iv=None, days=None, size=1.0,
                     wing_width_fraction=0.5):
    """Sell a call at the upper band edge, buy a higher one to cap it.

    The credit half of a bearish view, and the mirror of the bull put
    spread. Together the two are the wings of an iron condor, which this
    playbook could already build while being unable to build either half
    on its own.
    """
    spot = chain["spot"]
    band = _band(chain, iv, days)
    reference = band or (spot * 0.95, spot * 1.05)
    width = (reference[1] - reference[0]) * wing_width_fraction / 2.0

    short_opt = _closest(chain["calls"], reference[1])
    long_opt = _closest(chain["calls"], _strike(short_opt) + width)
    if _strike(long_opt) <= _strike(short_opt):
        return None
    legs = [
        Leg("call", -1, _mid(short_opt), strike=_strike(short_opt), qty=size,
            ref=short_opt),
        Leg("call", +1, _mid(long_opt), strike=_strike(long_opt), qty=size,
            ref=long_opt),
    ]
    plan = _plan("bear_call_spread", legs, chain, band)
    if plan["analysis"]["net_cash"] <= 0:
        return None
    return plan


def iron_condor(chain, iv=None, days=None, size=1.0,
                wing_width_fraction=0.5):
    """A put credit spread and a call credit spread together.

    Shorts sit at the band edges, so everything inside the 68 percent
    range is profit, and the wings sit half a band width beyond to cap the
    loss.
    """
    spot = chain["spot"]
    band = _band(chain, iv, days)
    # Strike selection needs a width even when no volatility was
    # available. The band itself stays as it was found, because the
    # plan reports it as the expected move and a five percent
    # stand-in is not one.
    reference = band or (spot * 0.95, spot * 1.05)
    width = (reference[1] - reference[0]) * wing_width_fraction / 2.0

    put_short = _closest(chain["puts"], reference[0])
    put_long = _closest(chain["puts"], _strike(put_short) - width)
    call_short = _closest(chain["calls"], reference[1])
    call_long = _closest(chain["calls"], _strike(call_short) + width)
    if (_strike(put_long) >= _strike(put_short)
            or _strike(call_long) <= _strike(call_short)):
        return None

    legs = [
        Leg("put", -1, _mid(put_short), strike=_strike(put_short), qty=size,
            ref=put_short),
        Leg("put", +1, _mid(put_long), strike=_strike(put_long), qty=size,
            ref=put_long),
        Leg("call", -1, _mid(call_short), strike=_strike(call_short),
            qty=size, ref=call_short),
        Leg("call", +1, _mid(call_long), strike=_strike(call_long), qty=size,
            ref=call_long),
    ]
    plan = _plan("iron_condor", legs, chain, band)
    # A condor that pays a debit is not a condor, it is a mistake with four
    # legs. Refuse rather than return something that cannot work.
    if plan["analysis"]["net_cash"] <= 0:
        return None
    return plan


def iron_butterfly(chain, iv=None, days=None, size=1.0,
                   wing_fraction=1.0):
    """Sell the at-the-money straddle, buy wings to cap it.

    A condor with the shorts pulled together to the money: more credit,
    narrower profit zone, and it needs the market to sit still rather than
    merely stay in a range.
    """
    spot = chain["spot"]
    band = _band(chain, iv, days)
    # Strike selection needs a width even when no volatility was
    # available. The band itself stays as it was found, because the
    # plan reports it as the expected move and a five percent
    # stand-in is not one.
    reference = band or (spot * 0.95, spot * 1.05)
    wing = (reference[1] - reference[0]) / 2.0 * wing_fraction

    short_call = _closest(chain["calls"], spot)
    short_put = _closest(chain["puts"], _strike(short_call))
    long_call = _closest(chain["calls"], _strike(short_call) + wing)
    long_put = _closest(chain["puts"], _strike(short_put) - wing)
    if (_strike(long_call) <= _strike(short_call)
            or _strike(long_put) >= _strike(short_put)):
        return None

    legs = [
        Leg("call", -1, _mid(short_call), strike=_strike(short_call),
            qty=size, ref=short_call),
        Leg("put", -1, _mid(short_put), strike=_strike(short_put), qty=size,
            ref=short_put),
        Leg("call", +1, _mid(long_call), strike=_strike(long_call), qty=size,
            ref=long_call),
        Leg("put", +1, _mid(long_put), strike=_strike(long_put), qty=size,
            ref=long_put),
    ]
    plan = _plan("iron_butterfly", legs, chain, band)
    if plan["analysis"]["net_cash"] <= 0:
        return None
    return plan


def long_call_butterfly(chain, iv=None, days=None, size=1.0,
                        wing_fraction=0.5):
    """Buy one lower call, sell two at the money, buy one higher.

    A cheap bet that the market pins near a strike. Small debit, small
    maximum gain, and it only pays if the underlying finishes close to the
    body.
    """
    spot = chain["spot"]
    band = _band(chain, iv, days)
    # Strike selection needs a width even when no volatility was
    # available. The band itself stays as it was found, because the
    # plan reports it as the expected move and a five percent
    # stand-in is not one.
    reference = band or (spot * 0.95, spot * 1.05)
    wing = (reference[1] - reference[0]) / 2.0 * wing_fraction

    body = _closest(chain["calls"], spot)
    lower = _closest(chain["calls"], _strike(body) - wing)
    upper = _closest(chain["calls"], _strike(body) + wing)
    if _strike(lower) >= _strike(body) or _strike(upper) <= _strike(body):
        return None

    legs = [
        Leg("call", +1, _mid(lower), strike=_strike(lower), qty=size,
            ref=lower),
        Leg("call", -1, _mid(body), strike=_strike(body), qty=2.0 * size,
            ref=body),
        Leg("call", +1, _mid(upper), strike=_strike(upper), qty=size,
            ref=upper),
    ]
    plan = _plan("long_call_butterfly", legs, chain, band)
    # A butterfly costing more than the distance between its strikes cannot
    # profit at any settlement price. Quoted chains produce this regularly
    # once spreads are wide or a strike is stale, and returning it would be
    # handing over a structure that is arithmetically dead. Refuse instead.
    if plan["analysis"]["max_gain"] <= 0:
        return None
    return plan


# ------------------------------------------------------------- asymmetric

def ratio_spread(chain, iv=None, days=None, size=1.0, ratio=2.0):
    """Buy one call near the money, sell more than one further out.

    Calls only, and that is deliberate. The short side is uncapped, which is
    the entire point of the structure: the payoff engine reports the loss as
    negative infinity because the slope above the top strike is negative and
    nothing bounds it. A put ratio would be the mirror image on paper, but
    the same engine bounds the downside at an underlying of zero, so its
    loss comes back as a large finite number. Calling that "unlimited" would
    be wrong, so this builder does not offer the put side rather than
    reporting one of the two under a label that only fits the other.

    The short strike is the furthest one the chain will finance without
    paying a debit. Further out is strictly safer here, so the credit
    constraint is what binds, and taking the furthest financed strike buys
    the widest tent and the highest upside breakeven available for nothing.

    A ratio spread that pays a debit is refused rather than returned. The
    registry carries one trade type per structure and this one is declared a
    credit, so a debit build would be labelled by the table as something the
    arithmetic says it is not.
    """
    if ratio <= 1.0:
        raise ValueError("a ratio spread sells more than it buys: ratio must "
                         "be greater than 1")
    spot = chain["spot"]
    band = _band(chain, iv, days)
    long_opt = _closest(chain["calls"], spot)
    best = None
    for short_opt in _priced(chain["calls"]):
        if _strike(short_opt) <= _strike(long_opt):
            continue
        legs = [
            Leg("call", +1, _mid(long_opt), strike=_strike(long_opt),
                qty=size, ref=long_opt),
            Leg("call", -1, _mid(short_opt), strike=_strike(short_opt),
                qty=ratio * size, ref=short_opt),
        ]
        if analyze(legs, spot=spot)["net_cash"] <= 0:
            continue
        # Strikes arrive sorted, so the last credit found is the furthest.
        best = legs
    if best is None:
        return None
    return _plan("ratio_spread", best, chain, band)


def broken_wing_butterfly(chain, iv=None, days=None, size=1.0,
                          wing_fraction=0.5, far_wing_multiple=2.0,
                          max_far_wing_multiple=3.0):
    """A call butterfly with the far wing wider than the near one.

    Skipping strikes on the upper wing makes the long leg out there cheaper
    than the symmetric one, which is what turns the debit of an ordinary
    butterfly into a credit. The credit is the whole reason to prefer this
    shape: below the lower strike every leg expires worthless and the credit
    is kept, so that side carries no risk at all. The price is above the
    upper strike, where the loss is the difference between the wings less
    the credit, which is larger than an ordinary butterfly can lose.

    The near wing comes from the expected move, as the ordinary butterfly's
    wings do. The far wing starts at far_wing_multiple times the near one
    and walks outward only until the structure pays a credit, so the extra
    risk taken is the least the chain will finance rather than the most it
    will allow. max_far_wing_multiple stops that walk: past it the far leg
    is so distant that it is a disaster hedge rather than a wing, and the
    structure is a ratio spread wearing a butterfly's name.

    A build that pays a debit is refused, on the same ground as the ratio
    spread: it would carry risk on both sides while the registry declares it
    a credit.
    """
    if far_wing_multiple <= 1.0:
        raise ValueError("the far wing must be wider than the near one: "
                         "far_wing_multiple must be greater than 1")
    spot = chain["spot"]
    band = _band(chain, iv, days)
    # Strike selection needs a width even when no volatility was available.
    # The band itself stays as it was found, because the plan reports it as
    # the expected move and a five percent stand-in is not one.
    reference = band or (spot * 0.95, spot * 1.05)
    near_target = (reference[1] - reference[0]) / 2.0 * wing_fraction

    body = _closest(chain["calls"], spot)
    lower = _closest(chain["calls"], _strike(body) - near_target)
    near_wing = _strike(body) - _strike(lower)
    if near_wing <= 0:
        return None

    for upper in _priced(chain["calls"]):
        far_wing = _strike(upper) - _strike(body)
        if far_wing + 1e-9 < near_wing * far_wing_multiple:
            continue
        if far_wing > near_wing * max_far_wing_multiple + 1e-9:
            break
        legs = [
            Leg("call", +1, _mid(lower), strike=_strike(lower), qty=size,
                ref=lower),
            Leg("call", -1, _mid(body), strike=_strike(body), qty=2.0 * size,
                ref=body),
            Leg("call", +1, _mid(upper), strike=_strike(upper), qty=size,
                ref=upper),
        ]
        if analyze(legs, spot=spot)["net_cash"] <= 0:
            continue
        return _plan("broken_wing_butterfly", legs, chain, band)
    return None


def jade_lizard(chain, iv=None, days=None, size=1.0):
    """A short put below the range plus a short call spread above it.

    The defining property is that there is no upside risk when the total
    credit is at least the width of the call spread: above the long call the
    payoff is flat at credit minus width, so the sign of that number decides
    whether a rally can cost anything. It is a property of the strikes and
    the premiums actually available, not of the shape, so it is measured
    from the payoff above the top strike and reported in the analysis as
    no_upside_risk rather than assumed.

    The long call is the furthest strike that keeps the property, because
    the further out it sits the cheaper it is and the larger the credit,
    and the credit is the maximum gain. When no strike keeps it, the
    narrowest call spread available is used, which is the least upside risk
    the chain offers, and the field says the property does not hold.

    The whole risk is the short put. It is bounded only by the underlying
    reaching zero, so size it as though assignment were certain.
    """
    spot = chain["spot"]
    band = _band(chain, iv, days)
    reference = band or (spot * 0.95, spot * 1.05)

    below = [p for p in _priced(chain["puts"])
             if _strike(p) <= reference[0]]
    if not below:
        return None
    short_put = max(below, key=_strike)
    short_call = _closest(chain["calls"], reference[1])
    higher = [c for c in _priced(chain["calls"])
              if _strike(c) > _strike(short_call)]
    if not higher:
        return None

    def _legs(long_call):
        return [
            Leg("put", -1, _mid(short_put), strike=_strike(short_put),
                qty=size, ref=short_put),
            Leg("call", -1, _mid(short_call), strike=_strike(short_call),
                qty=size, ref=short_call),
            Leg("call", +1, _mid(long_call), strike=_strike(long_call),
                qty=size, ref=long_call),
        ]

    def _covered(legs):
        """Is the payoff above the top strike still not a loss?

        Read from the payoff itself rather than compared against the width,
        so the answer stays true if the leg selection ever changes shape.
        """
        top = max(leg.strike for leg in legs if leg.strike is not None)
        return pnl_at_expiry(legs, top + 1.0) >= 0.0

    chosen = None
    for long_call in higher:
        legs = _legs(long_call)
        if analyze(legs, spot=spot)["net_cash"] <= 0:
            continue
        if _covered(legs):
            chosen = legs
    if chosen is None:
        chosen = _legs(higher[0])
        if analyze(chosen, spot=spot)["net_cash"] <= 0:
            return None

    plan = _plan("jade_lizard", chosen, chain, band)
    plan["analysis"]["no_upside_risk"] = bool(_covered(chosen))
    return plan


# ------------------------------------------------------------- the registry

PLAYBOOK = {
    "long_call": {
        "trade_type": "debit",
        "outlooks": (Outlook.STRONG_BULLISH,),
        "vol_view": "any",
        "needs_underlying": False,
        "when_to_use": ("Stock replacement, very bullish. Uncapped upside, "
                        "risk capped at the premium. Needs a strong move; a "
                        "mild one only pays if it happens fast."),
        "build": long_call,
    },
    "long_put": {
        "trade_type": "debit",
        "outlooks": (Outlook.STRONG_BEARISH,),
        "vol_view": "any",
        "needs_underlying": False,
        "when_to_use": ("Alternative to shorting: profits from the fall with "
                        "risk capped at the premium."),
        "build": long_put,
    },
    "bull_call_spread": {
        "trade_type": "debit",
        "outlooks": (Outlook.MILD_BULLISH,),
        "vol_view": "any",
        "needs_underlying": False,
        "when_to_use": ("Mildly bullish. Cheaper than a long call and it "
                        "reaches full profit on a normal move, at the cost "
                        "of a capped gain."),
        "build": bull_call_spread,
    },
    "bull_put_spread": {
        "trade_type": "credit",
        "outlooks": (Outlook.MILD_BULLISH, Outlook.NEUTRAL),
        "vol_view": "crush",
        "needs_underlying": False,
        "when_to_use": ("The credit half of a bullish view. Collects premium "
                        "and wins if the underlying does not fall through "
                        "the short strike, where a bull call spread pays a "
                        "debit and needs the rise to arrive. Loss is capped "
                        "by the lower long put."),
        "build": bull_put_spread,
    },
    "bear_call_spread": {
        "trade_type": "credit",
        "outlooks": (Outlook.MILD_BEARISH, Outlook.NEUTRAL),
        "vol_view": "crush",
        "needs_underlying": False,
        "when_to_use": ("The credit half of a bearish view, and the mirror "
                        "of the bull put spread. The two together are the "
                        "wings of an iron condor, which this playbook could "
                        "build while being unable to build either half."),
        "build": bear_call_spread,
    },
    "bear_put_spread": {
        "trade_type": "debit",
        "outlooks": (Outlook.MILD_BEARISH,),
        "vol_view": "any",
        "needs_underlying": False,
        "when_to_use": ("Mildly bearish. Higher probability than a long put "
                        "because a normal move is enough."),
        "build": bear_put_spread,
    },
    "cash_secured_put": {
        "trade_type": "credit",
        "outlooks": (Outlook.NEUTRAL, Outlook.MILD_BULLISH),
        "vol_view": "crush",
        "needs_underlying": False,
        "when_to_use": ("Neutral to mildly bullish, or a way to be paid "
                        "while waiting to own the underlying lower. Only "
                        "the extreme drop loses."),
        "build": cash_secured_put,
    },
    "covered_call": {
        "trade_type": "credit",
        "outlooks": (Outlook.NEUTRAL, Outlook.MILD_BULLISH),
        "vol_view": "crush",
        "needs_underlying": True,
        "when_to_use": ("Own the underlying and expect sideways to mildly "
                        "up. Collect premium; upside is capped at the short "
                        "strike."),
        "build": covered_call,
    },
    "protective_put": {
        "trade_type": "debit",
        "outlooks": (Outlook.STRONG_BULLISH, Outlook.STRONG_BEARISH),
        "vol_view": "expand",
        "needs_underlying": True,
        "when_to_use": ("Insurance on a position you own through a volatile "
                        "stretch: keep the upside, cap the downside."),
        "build": protective_put,
    },
    "straddle": {
        "trade_type": "debit",
        "outlooks": (Outlook.STRONG_BULLISH, Outlook.STRONG_BEARISH),
        "vol_view": "expand",
        "needs_underlying": False,
        "when_to_use": ("A big move is coming and the direction is unknown. "
                        "Dead money if nothing happens, and the most "
                        "expensive way to be wrong about timing."),
        "build": straddle,
    },
    "strangle": {
        "trade_type": "debit",
        "outlooks": (Outlook.STRONG_BULLISH, Outlook.STRONG_BEARISH),
        "vol_view": "expand",
        "needs_underlying": False,
        "when_to_use": ("Cheaper than a straddle with a flat bottom, but "
                        "the move has to be bigger to clear either wing."),
        "build": strangle,
    },
    "iron_condor": {
        "trade_type": "credit",
        "outlooks": (Outlook.NEUTRAL, Outlook.MILD_BULLISH,
                     Outlook.MILD_BEARISH),
        "vol_view": "crush",
        "needs_underlying": False,
        "when_to_use": ("Range bound with volatility expected to fall. "
                        "Everything inside the expected range is profit; "
                        "the wings cap what an extreme move can cost."),
        "build": iron_condor,
    },
    "iron_butterfly": {
        "trade_type": "credit",
        "outlooks": (Outlook.NEUTRAL,),
        "vol_view": "crush",
        "needs_underlying": False,
        "when_to_use": ("Pinned, not merely range bound. More credit than a "
                        "condor for a much narrower profit zone."),
        "build": iron_butterfly,
    },
    "long_call_butterfly": {
        "trade_type": "debit",
        "outlooks": (Outlook.NEUTRAL,),
        "vol_view": "crush",
        "needs_underlying": False,
        "when_to_use": ("A cheap bet on the market pinning near a strike. "
                        "Small debit, small maximum gain, needs the finish "
                        "to land close to the body."),
        "build": long_call_butterfly,
    },
    "ratio_spread": {
        "trade_type": "credit",
        "outlooks": (Outlook.NEUTRAL, Outlook.MILD_BULLISH),
        "vol_view": "crush",
        "needs_underlying": False,
        "when_to_use": ("A drift up that stalls, paid for by selling two "
                        "calls for every one bought. One of those shorts is "
                        "naked, so a strong rally loses without limit and "
                        "the maximum loss is reported as unlimited rather "
                        "than as a number. Read the upper breakeven against "
                        "the expected move before using it: on a chain that "
                        "only just finances the credit, that breakeven sits "
                        "inside the range the market already expects."),
        "build": ratio_spread,
    },
    "broken_wing_butterfly": {
        "trade_type": "credit",
        "outlooks": (Outlook.MILD_BEARISH, Outlook.NEUTRAL),
        "vol_view": "crush",
        "needs_underlying": False,
        "when_to_use": ("A butterfly with the far wing widened until it pays "
                        "a credit, which leaves nothing at risk below the "
                        "lower strike: every leg expires worthless there and "
                        "the credit is kept. The wider wing is what that "
                        "costs, and it is charged above the upper strike, "
                        "where the loss is the difference between the wings "
                        "less the credit. It still wants the finish near the "
                        "body, where the gain is largest."),
        "build": broken_wing_butterfly,
    },
    "jade_lizard": {
        "trade_type": "credit",
        "outlooks": (Outlook.MILD_BEARISH, Outlook.NEUTRAL,
                     Outlook.MILD_BULLISH),
        "vol_view": "crush",
        "needs_underlying": False,
        "when_to_use": ("A short put under the expected range and a short "
                        "call spread above it. When the credit is at least "
                        "the width of that call spread the structure cannot "
                        "lose on a rally at all; whether it holds for the "
                        "strikes actually chosen is measured and reported as "
                        "no_upside_risk in the analysis, so read the field "
                        "rather than assuming the shape. The whole risk is "
                        "the short put, so size it as though assignment "
                        "were certain."),
        "build": jade_lizard,
    },
    "calendar_spread": {
        "trade_type": "debit",
        "outlooks": (Outlook.NEUTRAL,),
        "vol_view": "expand",
        "needs_underlying": False,
        "needs_two_expiries": True,
        "when_to_use": ("Sell the near expiry, buy the far one at the same "
                        "strike, and collect the difference in decay. It "
                        "wants the underlying to sit still and the far "
                        "leg's volatility to hold up."),
        "build": None,
        "build_two_expiry": "calendar_spread",
    },
    "calendar_put_spread": {
        "trade_type": "debit",
        "outlooks": (Outlook.NEUTRAL,),
        "vol_view": "any",
        "needs_underlying": False,
        "needs_two_expiries": True,
        "when_to_use": ("The put side of the same time spread. It carries "
                        "the same decay difference and a different skew: "
                        "the put wing is usually the bid one, so the near "
                        "leg sold is richer and the far leg bought costs "
                        "more. Built as its own structure because a chain "
                        "can favour one side over the other and a page "
                        "showing only the call side cannot say which."),
        "build": None,
        "build_two_expiry": "calendar_spread",
        "kind": "put",
    },
    "diagonal_put_spread": {
        "trade_type": "debit",
        "outlooks": (Outlook.MILD_BEARISH,),
        "vol_view": "any",
        "needs_underlying": False,
        "needs_two_expiries": True,
        "when_to_use": ("The put side of the diagonal: the calendar's "
                        "carry with a downward lean rather than an upward "
                        "one."),
        "build": None,
        "build_two_expiry": "diagonal_spread",
        "kind": "put",
    },
    "ratio_call_diagonal": {
        "trade_type": "debit",
        "outlooks": (Outlook.MILD_BULLISH, Outlook.STRONG_BULLISH),
        "vol_view": "any",
        "needs_underlying": False,
        "needs_two_expiries": True,
        "when_to_use": ("Back-month long calls at 50 to 80 delta with fewer "
                        "front-month calls sold against them. The shorts "
                        "subsidise the carry while the delta ratio stays "
                        "below one, so a large move is not capped the way a "
                        "1x1 diagonal caps it. Two expiries."),
        "build": None,
        "build_two_expiry": "ratio_call_diagonal",
    },
    "ratio_put_diagonal": {
        "trade_type": "debit",
        "outlooks": (Outlook.MILD_BEARISH, Outlook.STRONG_BEARISH),
        "vol_view": "any",
        "needs_underlying": False,
        "needs_two_expiries": True,
        "when_to_use": ("The bearish mirror. Back-month long puts with "
                        "fewer front-month puts sold against them, delta "
                        "ratio held below one so the fall is not capped. "
                        "Two expiries."),
        "build": None,
        "build_two_expiry": "ratio_put_diagonal",
    },
    "diagonal_spread": {
        "trade_type": "debit",
        "outlooks": (Outlook.MILD_BULLISH, Outlook.MILD_BEARISH),
        "vol_view": "any",
        "needs_underlying": False,
        "needs_two_expiries": True,
        "kind": "call",
        "when_to_use": ("A calendar with different strikes: a directional "
                        "lean on top of the calendar's carry."),
        "build": None,
        "build_two_expiry": "diagonal_spread",
    },
}


def recommend(outlook, vol_view="neutral", owns_underlying=False,
              direction_known=True):
    """Rank the playbook for a view. Returns (name, score, meta), best first.

    The ranking is a stated heuristic, not a discovered edge: a strategy
    scores for matching the outlook, for matching the volatility view, and
    against paying for both directions when only one is expected. It says
    which structure fits a view, never whether the view is right.
    """
    outlook = Outlook(int(outlook))
    ranked = []
    for name, meta in PLAYBOOK.items():
        if meta["needs_underlying"] and not owns_underlying:
            continue
        two_sided = (Outlook.STRONG_BULLISH in meta["outlooks"]
                     and Outlook.STRONG_BEARISH in meta["outlooks"])
        score = 0.0
        if outlook in meta["outlooks"]:
            score += 2.0 + 0.25 / len(meta["outlooks"])
        elif any(abs(int(o) - int(outlook)) == 1 for o in meta["outlooks"]):
            score += 0.5
        if not direction_known:
            score = 2.0 if two_sided else 0.0
        elif two_sided:
            score *= 0.5
        if vol_view == "crush":
            if meta["vol_view"] == "crush":
                score += 1.0
            elif meta["vol_view"] == "expand":
                score -= 1.0
            elif meta["trade_type"] == "credit":
                score += 0.5
        elif vol_view == "expand":
            if meta["vol_view"] == "expand":
                score += 1.0
            elif meta["trade_type"] == "credit":
                score -= 1.0
        if score > 0:
            ranked.append((name, score, meta))
    ranked.sort(key=lambda item: (-item[1], item[0]))
    return ranked


def build(strategy, chain, **kwargs):
    """Build one plan by name. chain must come from split_chain."""
    meta = PLAYBOOK.get(strategy)
    if meta is None:
        raise KeyError("unknown strategy {!r}. Known: {}".format(
            strategy, ", ".join(sorted(PLAYBOOK))))
    if meta["build"] is None:
        if meta.get("build_two_expiry"):
            raise NotImplementedError(
                "{} spans two expiries, so it needs a second chain. Build "
                "it with build_time_spread(name, near_chain, far_chain), or "
                "from the command line with 'optiondesk strategy {} "
                "--far-snapshot PATH'.".format(strategy, strategy))
        raise NotImplementedError(
            "{} needs two expiries and the single expiry payoff engine "
            "cannot build it".format(strategy))
    return meta["build"](chain, **kwargs)


def describe(plan):
    """A readable block for logs and reports."""
    if plan is None:
        return "no viable plan"
    metrics = plan["analysis"]
    lines = [
        "{} ({} trade)".format(plan["strategy"], plan["trade_type"]),
        "outlook: " + ", ".join(plan["outlook_labels"]),
        "when: " + plan["when_to_use"],
        "legs:",
    ]
    lines += ["  {}".format(leg) for leg in plan["legs"]]
    lines.append("net {}: {:.2f}".format(metrics["trade_type"],
                                         abs(metrics["net_cash"])))
    lines.append("breakevens: " + (", ".join(
        "{:.2f}".format(b) for b in metrics["breakevens"]) or "none"))
    gain = ("unlimited" if metrics["max_gain"] == INF
            else "{:.2f}".format(metrics["max_gain"]))
    loss = ("unlimited" if metrics["max_loss"] == -INF
            else "{:.2f}".format(metrics["max_loss"]))
    lines.append("max gain: {}  max loss: {}".format(gain, loss))
    if metrics["reward_risk"]:
        lines.append("reward to risk: {:.2f} to 1".format(
            metrics["reward_risk"]))
    # Only the structures that measure it carry the key, and the ones that
    # do are the ones whose defining claim it is.
    if "no_upside_risk" in metrics:
        lines.append("no upside risk: {}".format(
            "yes" if metrics["no_upside_risk"] else "no"))
    return "\n".join(lines)
