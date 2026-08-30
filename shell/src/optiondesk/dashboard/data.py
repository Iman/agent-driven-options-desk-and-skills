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


def collect(directory, underlying=None, expiry=None):
    """Everything the page needs, for one selected group."""
    groups = index(directory)
    chosen = select(groups, underlying, expiry)
    if chosen is None:
        return {"artifact_dir": str(directory), "ladder": None,
                "ladder_path": None, "exposure": None, "exposure_path": None,
                "comparison": None, "plans": [], "groups": [],
                "selected": None, "simulation": None, "backtests": [],
                "term_structure": []}

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
