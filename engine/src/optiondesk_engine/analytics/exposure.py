"""Dealer gamma exposure, walls, and max pain from an option chain.

Copyright (C) 2026 Iman Samizadeh. Licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate written agreement.
The concepts follow the dealer gamma work in the author's 001-qaunt desk
(smartsheep.witty.analytics.gex and gamma_regime), reimplemented here
against this project's chain contract.

WHAT THIS IS, AND THE ASSUMPTION IT RESTS ON. Gamma exposure asks what
market makers would have to buy or sell to stay delta neutral as the
underlying moves. The arithmetic is exact; the sign convention is not. It
assumes dealers are long calls and short puts against the public, which is
the conventional assumption and is regularly wrong for individual names,
particularly around events and in heavily retail-traded tickers. Positive
net exposure is read as hedging that dampens moves, negative as hedging
that amplifies them.

That assumption is stated in the output as well as here, because a number
this easy to quote is a number that travels without its caveat.

Units: exposure is expressed per one percent move in the underlying, in
the underlying's quote currency, which is the convention that makes the
numbers comparable across strikes and underlyings.
"""

CONTRACT_MULTIPLIER = 100.0


def _usable(contract):
    return (contract.get("gamma") is not None
            and contract.get("open_interest") is not None
            and contract.get("strike") is not None)


def chain_exposure(contracts, spot, multiplier=CONTRACT_MULTIPLIER):
    """Gamma exposure by strike, the walls, and the flip level.

    contracts must carry gamma (from the Greek ladder) plus open interest
    and strike. Contracts missing any of the three are counted as skipped
    rather than treated as zero: an absent open interest is not the same
    as no open interest, and treating it as zero quietly moves every wall.

    Returns per-strike rows, the call and put walls, the estimated gamma
    flip level, and the totals, with the sign convention stated inline.
    """
    if spot is None or spot <= 0:
        raise ValueError("spot must be positive")

    by_strike = {}
    skipped = 0
    call_oi = put_oi = 0
    call_volume = put_volume = 0

    for contract in contracts:
        kind = contract.get("type")
        if kind not in ("call", "put"):
            skipped += 1
            continue
        volume = contract.get("volume") or 0
        if kind == "call":
            call_volume += int(volume)
        else:
            put_volume += int(volume)
        if not _usable(contract):
            skipped += 1
            continue
        strike = float(contract["strike"])
        open_interest = int(contract["open_interest"])
        gamma = float(contract["gamma"])
        if kind == "call":
            call_oi += open_interest
        else:
            put_oi += open_interest

        # Exposure per one percent move, in the underlying's quote
        # currency. gamma * S * 0.01 is the delta change over a one percent
        # move in share terms; multiplying by S again converts that share
        # delta into currency, and the multiplier and open interest scale
        # it to the whole strike.
        exposure = gamma * open_interest * multiplier * spot * spot * 0.01
        signed = exposure if kind == "call" else -exposure

        row = by_strike.setdefault(strike, {
            "strike": strike, "call_gex": 0.0, "put_gex": 0.0,
            "net_gex": 0.0, "call_oi": 0, "put_oi": 0,
        })
        row["call_gex" if kind == "call" else "put_gex"] += signed
        row["net_gex"] += signed
        row["call_oi" if kind == "call" else "put_oi"] += open_interest

    rows = sorted(by_strike.values(), key=lambda r: r["strike"])
    if not rows:
        return {
            "rows": [], "net_gex": 0.0, "call_wall": None, "put_wall": None,
            "gamma_flip": None, "skipped": skipped,
            "put_call_oi_ratio": None, "put_call_volume_ratio": None,
            "assumption": _ASSUMPTION,
        }

    running = 0.0
    for row in rows:
        running += row["net_gex"]
        row["cumulative_gex"] = running

    # A chain with no calls at all made max() return the first row with a
    # gamma of exactly zero, which was then reported as the call wall.
    call_candidates = [r for r in rows if r["call_gex"] > 0]
    put_candidates = [r for r in rows if r["put_gex"] < 0]
    call_wall = (max(call_candidates, key=lambda r: r["call_gex"])
                 if call_candidates else None)
    put_wall = (min(put_candidates, key=lambda r: r["put_gex"])
                if put_candidates else None)

    # Every level where cumulative exposure crosses zero, linearly
    # interpolated between the straddling strikes. An earlier version
    # returned the first crossing and stopped, so a profile crossing five
    # times reported the lowest one: at spot 100 it read "flip 81.67" while
    # the nearest crossings were at 96.79 and 102.50. The headline is now
    # the crossing nearest spot, and the rest are returned with it.
    crossings = []
    for previous, current in zip(rows, rows[1:]):
        y0, y1 = previous["cumulative_gex"], current["cumulative_gex"]
        if (y0 < 0 <= y1) or (y0 > 0 >= y1):
            span = y1 - y0
            if span == 0:
                crossings.append(current["strike"])
            else:
                crossings.append(previous["strike"] + (0 - y0) * (
                    current["strike"] - previous["strike"]) / span)
    flip = (min(crossings, key=lambda level: abs(level - spot))
            if crossings else None)

    return {
        "rows": rows,
        "net_gex": running,
        "call_wall": ({"strike": call_wall["strike"],
                       "gex": call_wall["call_gex"]} if call_wall else None),
        "put_wall": ({"strike": put_wall["strike"],
                      "gex": put_wall["put_gex"]} if put_wall else None),
        "gamma_flip": flip,
        "gamma_flip_all": crossings,
        "gamma_flip_note": (
            "The crossing nearest spot. There {} {} crossing(s) in total, "
            "listed in gamma_flip_all. The cumulative profile starts at the "
            "lowest LISTED strike rather than at zero, so extending the "
            "strike ladder shifts the whole profile and can move every "
            "level.".format("is" if len(crossings) == 1 else "are",
                            len(crossings))),
        "spot": spot,
        "regime": ("dampening" if running > 0 else "amplifying"),
        "skipped": skipped,
        "call_open_interest": call_oi,
        "put_open_interest": put_oi,
        "put_call_oi_ratio": (put_oi / call_oi) if call_oi else None,
        "put_call_volume_ratio": ((put_volume / call_volume)
                                  if call_volume else None),
        "assumption": _ASSUMPTION,
    }


_ASSUMPTION = (
    "Signs assume dealers are long calls and short puts against the "
    "public. That convention is often wrong for a single name, especially "
    "around events and in heavily retail-traded tickers, and the walls "
    "move with it. Exposure is per one percent move in the underlying."
)


def max_pain(contracts, multiplier=CONTRACT_MULTIPLIER):
    """The strike where option holders collect the least at expiry.

    For every listed strike, sum what all open contracts would pay out if
    the underlying settled there. The minimum is the conventional max pain
    level. It is a description of where open interest sits, not a forecast
    of where price goes, and the evidence that price gravitates to it is
    thin. It is reported because traders ask for it, with that caveat
    attached.
    """
    priced = [c for c in contracts
              if c.get("open_interest") is not None
              and c.get("strike") is not None
              and c.get("type") in ("call", "put")]
    if not priced:
        return None
    # Every strike pays out zero when nothing is open, and the minimum then
    # falls on whichever strike happens to be lowest. That is a number
    # derived from no information, so it is refused.
    if sum(int(c["open_interest"]) for c in priced) <= 0:
        return None

    strikes = sorted({float(c["strike"]) for c in priced})
    profile = []
    for settle in strikes:
        payout = 0.0
        for contract in priced:
            strike = float(contract["strike"])
            open_interest = int(contract["open_interest"])
            if contract["type"] == "call":
                payout += max(settle - strike, 0.0) * open_interest
            else:
                payout += max(strike - settle, 0.0) * open_interest
        profile.append({"strike": settle, "payout": payout * multiplier})

    best = min(profile, key=lambda p: p["payout"])
    return {
        "strike": best["strike"],
        "payout_at_strike": best["payout"],
        "profile": profile,
        "note": ("The strike at which open contracts pay out least. It "
                 "describes where open interest sits, not where price is "
                 "going."),
    }
