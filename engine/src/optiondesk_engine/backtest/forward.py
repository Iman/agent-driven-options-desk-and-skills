"""Forward testing: mark a registered position against later quotes.

Copyright (C) 2026 Iman Samizadeh. Licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate written agreement.

A backtest asks what a rule would have done. A forward test asks what a
position actually did, from the moment it was written down, against quotes
that arrived afterwards. The difference matters because the second cannot
be tuned after the fact: the entry is fixed before the outcome is known.

WHAT IS AND IS NOT CLAIMED. This is paper. Entry and exit marks come from
snapshot mid quotes, so they still are not fills, and a real entry would
have crossed a spread. What a forward test does remove is hindsight: the
structure, the strikes and the entry mark are recorded before any of the
marking data exists. That is a weaker claim than a live track record and a
much stronger one than a backtest.

Marking rules, chosen so a stale or partial chain cannot quietly flatter a
position:

  - A leg is marked at the mid of the same contract symbol where the later
    chain carries it, and by strike and type where it does not.
  - A leg that cannot be found is not marked at zero. The whole position is
    reported as unmarkable, with the missing legs named.
  - A leg whose mark comes from a last trade rather than a two-sided quote
    is flagged, because that is a different quality of number.
"""


def _match(contracts, leg):
    """Find the later quote for one leg: by symbol, else by strike and type."""
    symbol = (leg.get("symbol") or "").strip()
    if symbol:
        for contract in contracts:
            if (contract.get("symbol") or "").strip() == symbol:
                return contract, "symbol"
    strike = leg.get("strike")
    if strike is None:
        return None, None
    for contract in contracts:
        if (contract.get("type") == leg.get("kind")
                and abs(float(contract["strike"]) - float(strike)) < 1e-9):
            return contract, "strike"
    return None, None


def _mid(contract):
    if contract.get("mid") is not None:
        return float(contract["mid"]), contract.get("mid_source") or "quote"
    bid, ask = contract.get("bid"), contract.get("ask")
    if bid is not None and ask is not None:
        return (float(bid) + float(ask)) / 2.0, "quote"
    if contract.get("last") is not None:
        return float(contract["last"]), "last_trade"
    return None, None


def mark_position(position, snapshot):
    """Mark one recorded position against a later chain snapshot.

    position carries the legs as they were written down, each with kind,
    side, strike, qty, and the entry price. snapshot is a chain snapshot
    taken later. Returns the mark, the profit against entry, and every
    reason the mark might be worse than it looks.
    """
    contracts = snapshot.get("contracts") or []
    spot = float(snapshot["spot"])

    marked_legs = []
    problems = []
    stale_marks = 0
    value = 0.0
    for leg in position["legs"]:
        if leg["kind"] == "underlying":
            # The underlying leg marks at spot, which is always available.
            sign = 1 if leg["side"] == "long" else -1
            leg_value = sign * float(leg["qty"]) * spot
            value += leg_value
            marked_legs.append(dict(leg, mark=spot, mark_source="spot",
                                    value=leg_value))
            continue

        contract, how = _match(contracts, leg)
        if contract is None:
            problems.append("no later quote for {} {} at {}".format(
                leg["side"], leg["kind"], leg.get("strike")))
            marked_legs.append(dict(leg, mark=None, mark_source=None,
                                    value=None))
            continue

        mark, source = _mid(contract)
        if mark is None:
            problems.append("{} {} at {} has no usable mark".format(
                leg["side"], leg["kind"], leg.get("strike")))
            marked_legs.append(dict(leg, mark=None, mark_source=None,
                                    value=None))
            continue
        if source == "last_trade":
            stale_marks += 1

        sign = 1 if leg["side"] == "long" else -1
        leg_value = sign * float(leg["qty"]) * mark
        value += leg_value
        marked_legs.append(dict(leg, mark=mark, mark_source=source,
                                matched_by=how, value=leg_value))

    if problems:
        return {
            "markable": False,
            "problems": problems,
            "legs": marked_legs,
            "spot": spot,
            "as_of": snapshot.get("meta", {}).get("generated_utc"),
            "note": ("Some legs have no later quote, so the position is not "
                     "marked. A missing leg is not a leg worth nothing, and "
                     "treating it as zero would report a profit that does "
                     "not exist."),
        }

    entry_value = 0.0
    for leg in position["legs"]:
        sign = 1 if leg["side"] == "long" else -1
        entry_value += sign * float(leg["qty"]) * float(leg["price"])

    notes = []
    if stale_marks:
        notes.append("{} leg(s) marked from a last trade rather than a "
                     "two-sided quote".format(stale_marks))

    return {
        "markable": True,
        "problems": [],
        "legs": marked_legs,
        "spot": spot,
        "as_of": snapshot.get("meta", {}).get("generated_utc"),
        "entry_value": entry_value,
        "mark_value": value,
        "profit": value - entry_value,
        "underlying_move": spot / float(position["entry_spot"]) - 1.0,
        "stale_marks": stale_marks,
        "notes": notes,
        "note": ("Marked at snapshot mid quotes. Not fills: a real entry "
                 "would have crossed the spread on every leg, and a real "
                 "exit would cross it again."),
    }


def settle_position(position, settlement_price, pnl_at_expiry, legs_builder):
    """Settle a position at expiry against a final underlying price."""
    legs = legs_builder(position["legs"])
    profit = pnl_at_expiry(legs, float(settlement_price))
    return {
        "settlement_price": float(settlement_price),
        "profit": profit,
        "underlying_move": (float(settlement_price)
                            / float(position["entry_spot"]) - 1.0),
        "note": ("Settled against the underlying's price at expiry, so this "
                 "profit is free of any mark quality question. It still "
                 "assumes the entry was achieved at the recorded mid."),
    }
