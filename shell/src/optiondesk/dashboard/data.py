"""Collect artifacts from disk into the shape the dashboard page needs.

Artifacts are grouped by underlying and expiry, because that pair is what a
reader actually chooses between. Anything the group is missing is reported
as missing rather than filled in from another expiry, which would silently
mix a September ladder with an October chain.

Kept apart from rendering so the page is a pure function of this data, and
so selection can be tested without parsing HTML.
"""

from pathlib import Path

from optiondesk.artifacts import read_json

KINDS = ("chain", "greeks", "exposure", "comparison", "strategy",
         "simulation", "backtest")

# One file for the whole desk rather than one per underlying and expiry,
# and it carries no underlying key, so it is read whole rather than indexed
# into a group. Not in KINDS for that reason.
LEDGER = "forward_ledger.json"


def _load(path):
    """Read one artifact, or None.

    A file that parses cleanly but is not an object is skipped like an
    unreadable one. A JSON array in the artifact directory previously
    reached .get() and raised AttributeError from a listing routine.
    """
    try:
        payload = read_json(path)
    except (ValueError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def index(directory):
    """Every (underlying, expiry) group on disk, newest group first.

    A group carries the newest artifact of each kind, every strategy plan
    found for it, and the timestamp of the most recent thing in it.
    """
    target = Path(directory)
    if not target.exists():
        return []

    groups = {}
    for path in sorted(target.glob("*.json"),
                       key=lambda p: p.stat().st_mtime, reverse=True):
        kind = path.name.split("_")[0]
        if kind not in KINDS:
            continue
        payload = _load(path)
        if payload is None:
            continue
        underlying = payload.get("underlying")
        if not underlying:
            continue
        key = (underlying, payload.get("expiry")
               if kind not in ("simulation", "backtest") else None)
        group = groups.setdefault(key, {
            "underlying": underlying,
            "expiry": payload.get("expiry"),
            "artifacts": {},
            "plans": [],
            "paths": {},
            "mtime": 0.0,
            "spot": payload.get("spot"),
        })
        group["mtime"] = max(group["mtime"], path.stat().st_mtime)
        if kind == "strategy":
            if not any(p.get("strategy") == payload.get("strategy")
                       for p in group["plans"]):
                payload["_path"] = str(path)
                group["plans"].append(payload)
        elif kind == "backtest":
            group.setdefault("backtests", []).append(payload)
        elif kind not in group["artifacts"]:
            group["artifacts"][kind] = payload
            group["paths"][kind] = str(path)

    ordered = sorted(groups.values(), key=lambda g: g["mtime"], reverse=True)
    for group in ordered:
        group["plans"].sort(key=lambda p: p.get("strategy") or "")
        # A group holding only a simulation or a backtest is not a chain
        # view: neither belongs to an expiry, and offering it in the picker
        # would present an empty desk.
        group["selectable"] = bool(
            set(group["artifacts"]) - {"simulation", "backtest"}
            or group["plans"])
    return ordered


def select(groups, underlying=None, expiry=None):
    """The requested group, or the most recently touched one.

    An underlying with no expiry given selects that underlying's newest
    expiry, which is what someone clicking a ticker means.
    """
    groups = [g for g in groups if g.get("selectable", True)]
    if not groups:
        return None
    candidates = groups
    if underlying:
        wanted = underlying.upper()
        candidates = [g for g in groups
                      if (g["underlying"] or "").upper() == wanted] or groups
    if expiry:
        exact = [g for g in candidates if g["expiry"] == expiry]
        if exact:
            return exact[0]
    return candidates[0]


def forward_ledger(directory):
    """The forward ledger, or None when no position has ever been opened.

    The pipeline figure lists the ledger among the artifacts the page
    reads, and until this was added the page never opened it.
    """
    path = Path(directory) / LEDGER
    if not path.exists():
        return None
    return _load(path)


def collect(directory, underlying=None, expiry=None):
    """Everything the page needs, for one selected group."""
    groups = index(directory)
    chosen = select(groups, underlying, expiry)
    if chosen is None:
        return {"artifact_dir": str(directory), "ladder": None,
                "ladder_path": None, "exposure": None, "exposure_path": None,
                "comparison": None, "plans": [], "groups": [],
                "selected": None, "simulation": None, "backtests": [],
                "term_structure": [], "surface": None,
                "variance_premium": None, "condors": [],
                "forward_ledger": forward_ledger(directory)}

    # A simulation or a backtest belongs to the underlying, not to one
    # expiry, so it is looked up across every group for that symbol rather
    # than only in the selected one.
    symbol = (chosen["underlying"] or "").upper()
    simulation = None
    backtests = []
    for group in groups:
        if (group["underlying"] or "").upper() != symbol:
            continue
        if simulation is None and group["artifacts"].get("simulation"):
            simulation = group["artifacts"]["simulation"]
        backtests.extend(group.get("backtests") or [])
    backtests.sort(key=lambda b: (b.get("strategy") or ""))

    # Term structure: at-the-money volatility and skew across every expiry
    # on disk for this underlying, which needs more than the selected group.
    term_structure = []
    for group in groups:
        if (group["underlying"] or "").upper() != symbol:
            continue
        exposure_artifact = group["artifacts"].get("exposure")
        if not exposure_artifact or not exposure_artifact.get("smile"):
            continue
        smile = exposure_artifact["smile"]
        term_structure.append({
            "expiry": exposure_artifact.get("expiry"),
            "days": exposure_artifact.get("days_to_expiry"),
            "atm_iv": smile.get("atm_iv"),
            "risk_reversal": smile.get("risk_reversal"),
            "butterfly": smile.get("butterfly"),
            "expected_move": smile.get("expected_move"),
        })
    term_structure = [row for row in term_structure if row["days"]]
    term_structure.sort(key=lambda row: row["days"])

    return {
        "artifact_dir": str(directory),
        "term_structure": term_structure,
        # Across every expiry for this underlying, like the term structure
        # above and for the same reason: one chain cannot show either.
        "surface": volatility_surface(groups, symbol),
        "variance_premium": variance_premium(term_structure, simulation),
        "condors": condor_candidates(groups, symbol),
        # Desk-wide, like the file: every position, whatever its
        # underlying, so the panel matches what `optiondesk forward
        # status` prints.
        "forward_ledger": forward_ledger(directory),
        "simulation": simulation,
        "backtests": backtests,
        "ladder": chosen["artifacts"].get("greeks"),
        "ladder_path": chosen["paths"].get("greeks"),
        "exposure": chosen["artifacts"].get("exposure"),
        "exposure_path": chosen["paths"].get("exposure"),
        "comparison": chosen["artifacts"].get("comparison"),
        "chain": chosen["artifacts"].get("chain"),
        "plans": chosen["plans"],
        "selected": {"underlying": chosen["underlying"],
                     "expiry": chosen["expiry"],
                     "spot": chosen["spot"],
                     "have": sorted(chosen["artifacts"]),
                     "plan_count": len(chosen["plans"])},
        "groups": [
            {"underlying": g["underlying"], "expiry": g["expiry"],
             "have": sorted(g["artifacts"]), "plans": len(g["plans"]),
             "spot": g["spot"]}
            for g in groups if g.get("selectable")
        ],
    }


def volatility_surface(groups, symbol):
    """Implied volatility by strike and expiry, from every chain on disk.

    One point per listed contract, placed at its own strike and its own
    chain's days to expiry. Nothing is interpolated between listed strikes
    or between expiries: a gap in the grid is a strike that is not listed,
    and a far expiry quoting every fifth strike looks sparser than a near
    one quoting every strike because it is.

    The out-of-the-money side is taken at each strike, puts below that
    chain's spot and calls at or above it. Both sides quote a volatility at
    the same strike and they disagree; plotting both would put two values
    in one cell, and the out-of-the-money side is the one that is traded.
    """
    expiries = []
    points = []
    for group in groups:
        if (group["underlying"] or "").upper() != symbol:
            continue
        chain = group["artifacts"].get("chain")
        if not chain:
            continue
        days = chain.get("days_to_expiry")
        spot = chain.get("spot")
        if not days or not spot:
            continue
        taken = {}
        for contract in chain.get("contracts", []):
            strike = contract.get("strike")
            iv = contract.get("iv")
            if strike is None or not iv:
                continue
            if contract.get("type") != ("put" if strike < spot else "call"):
                continue
            taken[strike] = iv
        if not taken:
            continue
        expiry = chain.get("expiry")
        expiries.append({"expiry": expiry, "days": days, "spot": spot,
                         "strikes": len(taken)})
        for strike in sorted(taken):
            points.append([strike, days, taken[strike], expiry])

    # One expiry is a smile, not a surface, and the smile already has its
    # own panel. Two is the least that shows a term dimension at all.
    if len(expiries) < 2:
        return None
    expiries.sort(key=lambda row: row["days"])
    return {"points": points, "expiries": expiries}


def variance_premium(term_structure, simulation):
    """At-the-money implied volatility against the volatility shown.

    Implied comes from each expiry's smile, realised from the simulation's
    history block. Both are annualised, so the difference is in volatility
    points and needs no conversion.

    The axis is days to expiry, not calendar time. No artifact on disk
    carries a realised-volatility series through time: the simulation
    records one figure over one window, so a premium through calendar time
    cannot be drawn from what is here and is not drawn.
    """
    if not simulation:
        return None
    history = simulation.get("history") or {}
    realised = history.get("annualised_volatility")
    if realised is None:
        return None
    rows = []
    for row in term_structure or []:
        implied = row.get("atm_iv")
        if implied is None or not row.get("days"):
            continue
        rows.append({"expiry": row.get("expiry"), "days": row["days"],
                     "implied": implied, "realised": realised,
                     "gap": implied - realised})
    if len(rows) < 2:
        return None
    rows.sort(key=lambda row: row["days"])
    return {"rows": rows, "realised": realised,
            "history": {"observations": history.get("observations"),
                        "first": history.get("first"),
                        "last": history.get("last"),
                        "period": history.get("period")}}


def condor_candidates(groups, symbol):
    """Structures with two short strikes, with the width between them.

    The width and the wing distance are measured off the plan's own legs.
    The scores come from the comparison artifact of the same group, so a
    plan whose expiry has never been compared carries no score and is left
    out rather than scored against another expiry's ordering.

    This is not a search across the chain. Nothing on disk enumerates the
    condors a chain admits and no engine function builds more than the one
    the playbook picks, so what is here is the structures that exist as
    artifacts, across every expiry on file for this underlying.
    """
    out = []
    for group in groups:
        if (group["underlying"] or "").upper() != symbol:
            continue
        comparison = group["artifacts"].get("comparison")
        scored = {}
        for row in ((comparison or {}).get("rows") or []):
            scored[row.get("strategy")] = row
        for plan in group.get("plans") or []:
            legs = plan.get("legs") or []
            shorts = sorted(leg["strike"] for leg in legs
                            if leg.get("side") == "short"
                            and leg.get("strike") is not None)
            if len(shorts) < 2:
                continue
            row = scored.get(plan.get("strategy"))
            if not row or row.get("expected_return_on_risk") is None:
                continue
            longs = sorted(leg["strike"] for leg in legs
                           if leg.get("side") == "long"
                           and leg.get("strike") is not None)
            width = shorts[-1] - shorts[0]
            wing = None
            if len(longs) >= 2:
                wing = (longs[-1] - longs[0] - width) / 2.0
            out.append({
                "strategy": plan.get("strategy"),
                "expiry": plan.get("expiry"),
                "days": plan.get("days_to_expiry"),
                "short_low": shorts[0],
                "short_high": shorts[-1],
                "width": width,
                "wing": wing,
                "expected_return_on_risk": row.get("expected_return_on_risk"),
                "probability_of_profit": row.get("probability_of_profit"),
                "capital_at_risk": row.get("capital_at_risk"),
                "net_cash": row.get("net_cash"),
                "max_loss": row.get("max_loss"),
                "friction_verdict": row.get("friction_verdict"),
                "rank": row.get("rank"),
            })
    out.sort(key=lambda row: (row["width"], row["expiry"] or "",
                              row["strategy"] or ""))
    return out


def chain_series(chain):
    """Volume and open interest by strike, straight from the snapshot.

    The ladder only carries the graded band, and volume is not in it at
    all, so these come from the chain rather than from the Greeks.
    """
    if not chain:
        return {"calls": [], "puts": []}
    out = {"calls": [], "puts": []}
    for contract in chain.get("contracts", []):
        bucket = "calls" if contract.get("type") == "call" else "puts"
        out[bucket].append({
            "strike": contract.get("strike"),
            "volume": contract.get("volume") or 0,
            "open_interest": contract.get("open_interest") or 0,
            "iv": contract.get("iv"),
            "mid": contract.get("mid"),
        })
    for bucket in out.values():
        bucket.sort(key=lambda row: row["strike"])
    return out


def ladder_series(ladder):
    """Split a ladder into call and put series for plotting."""
    if not ladder:
        return {"calls": [], "puts": []}
    out = {"calls": [], "puts": []}
    for row in ladder.get("rows", []):
        bucket = "calls" if row["type"] == "call" else "puts"
        out[bucket].append({
            "strike": row["strike"], "iv": row.get("iv"),
            "price": row.get("price"), "delta": row.get("delta"),
            "gamma": row.get("gamma"), "vega": row.get("vega"),
            "theta": row.get("theta"), "vanna": row.get("vanna"),
            "charm": row.get("charm"),
        })
    for bucket in out.values():
        bucket.sort(key=lambda r: r["strike"])
    return out
