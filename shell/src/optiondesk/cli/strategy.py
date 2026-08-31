"""optiondesk strategy: build a multi-leg strategy from a chain snapshot.

Turns a snapshot into a concrete plan: the legs, the expiry risk graph,
model probabilities, net position Greeks, an estimate of what the round
trip costs at the quoted spreads, and the payoff curve for plotting.

Premiums come from snapshot mid quotes and a pricing model. They are not
executable prices. A plan is an analysis of a structure, not an order and
not a recommendation.
"""

import argparse
import json

from optiondesk import engine_bridge
from optiondesk.artifacts import (
    artifact_dir,
    envelope,
    latest,
    read_json,
    write_json,
)
from optiondesk.contracts import SCHEMA_FILES, STRATEGY_PLAN, validate

CURVE_POINTS = 240
# How far either side of spot the payoff curve runs when no volatility band
# is available. Wide enough to show where an unbounded leg is heading.
FALLBACK_SPAN = 0.25


def add_arguments(parser):
    """Register structure selection and the view that drives a recommendation:
    a named structure or recommend, the near and far snapshots, kind, offset,
    size, underlying entry, volatility view, whether the underlying is owned,
    whether direction is unknown, and output directory.
    """
    parser.add_argument("name", nargs="?", default=None,
                        help="strategy to build. Omit with --list or "
                             "--recommend")
    parser.add_argument("--snapshot", default=None,
                        help="chain snapshot path. Default: most recent")
    parser.add_argument("--far-snapshot", default=None, dest="far_snapshot",
                        help="the later expiry, for a calendar or diagonal. "
                             "Omit and the newest later chain for the same "
                             "underlying is used")
    parser.add_argument("--kind", default="call", choices=("call", "put"),
                        help="which side a time spread is built from")
    parser.add_argument("--offset", type=float, default=0.03,
                        help="how far out of the money a diagonal sells the "
                             "near leg, as a fraction of spot")
    parser.add_argument("--size", type=float, default=1.0,
                        help="contracts per leg")
    parser.add_argument("--underlying-entry", type=float, default=None,
                        dest="underlying_entry",
                        help="entry price for strategies holding the "
                             "underlying. Default: spot")
    parser.add_argument("--list", action="store_true", dest="list_only",
                        help="list the playbook and exit")
    parser.add_argument("--recommend", default=None,
                        help="rank strategies for an outlook: an integer "
                             "from -2 (strong bearish) to +2 (strong "
                             "bullish)")
    parser.add_argument("--vol-view", default="neutral", dest="vol_view",
                        choices=("neutral", "crush", "expand"),
                        help="expected direction of implied volatility")
    parser.add_argument("--owns-underlying", action="store_true",
                        dest="owns_underlying",
                        help="include strategies that need a holding")
    parser.add_argument("--direction-unknown", action="store_true",
                        dest="direction_unknown",
                        help="a move is expected but not its direction")
    parser.add_argument("--out-dir", default=None,
                        help="artifact directory override")
    return parser


def _find_far_snapshot(snapshot, near_path, out_dir):
    """The nearest later expiry for the same underlying, or None.

    Nearest rather than furthest: a calendar against an expiry a year out
    is a different trade from one a month out, and the month is what
    someone asking for a calendar almost always means.
    """
    from pathlib import Path

    directory = Path(out_dir) if out_dir else artifact_dir()
    near_days = float(snapshot["days_to_expiry"])
    best = None
    for candidate in directory.glob("chain_{}_*.json".format(
            str(snapshot["underlying"]).upper())):
        if str(candidate) == str(near_path):
            continue
        try:
            other = read_json(candidate)
        except (ValueError, OSError):
            continue
        if not isinstance(other, dict):
            continue
        days = other.get("days_to_expiry")
        if days is None or float(days) <= near_days:
            continue
        if best is None or float(days) < float(best[0]["days_to_expiry"]):
            best = (other, str(candidate))
    return best


def _nearest_chain(underlying, out_dir):
    """The soonest expiry on disk for one underlying.

    A time spread needs its near leg to be the near one. Falling back to
    "the most recent artifact" picks whichever chain was pulled last, and
    pulling the far month after the near one then made a calendar refuse
    to build because there was nothing later still.
    """
    from pathlib import Path

    directory = Path(out_dir) if out_dir else artifact_dir()
    best = None
    for candidate in directory.glob("chain_{}_*.json".format(
            (underlying or "").upper())):
        try:
            other = read_json(candidate)
        except (ValueError, OSError):
            continue
        if not isinstance(other, dict):
            continue
        days = other.get("days_to_expiry")
        if days is None:
            continue
        if best is None or float(days) < float(best[0]["days_to_expiry"]):
            best = (other, str(candidate))
    return best


def _time_spread(args, engine, engine_strategies, snapshot, path):
    """Build a calendar or diagonal, which needs a second chain."""
    if not args.snapshot:
        nearest = _nearest_chain(snapshot.get("underlying"), args.out_dir)
        if nearest is not None:
            snapshot, path = nearest
    if args.far_snapshot:
        far_snapshot = read_json(args.far_snapshot)
        far_path = args.far_snapshot
    else:
        found = _find_far_snapshot(snapshot, path, args.out_dir)
        if found is None:
            raise FileNotFoundError(
                "{} spans two expiries and no later chain for {} is on "
                "disk. Pull one with 'optiondesk chain {} --expiry "
                "YYYY-MM-DD', or pass --far-snapshot PATH.".format(
                    args.name, snapshot["underlying"],
                    snapshot["underlying"]))
        far_snapshot, far_path = found

    # Read before the not-built return below, which reports on this
    # snapshot and has to be able to say it was degraded.
    source_meta = snapshot.get("meta", {})
    near = engine_strategies.split_chain(snapshot)
    far = engine_strategies.split_chain(far_snapshot)
    plan = engine_strategies.build_time_spread(
        args.name, near, far, kind=args.kind, size=args.size,
        **({"offset": args.offset} if args.name == "diagonal_spread" else {}))
    if plan is None:
        return {
            "strategy": args.name,
            "built": False,
            "degraded": bool(source_meta.get("degraded")),
            "degraded_reason": source_meta.get("degraded_reason"),
            "reason": ("no viable structure across these two expiries: the "
                       "strikes or quotes did not admit one"),
            "source_artifact": str(path),
            "far_artifact": str(far_path),
        }

    analysis = dict(plan["analysis"])
    analysis["max_gain"] = _jsonable(analysis["max_gain"])
    analysis["max_loss"] = _jsonable(analysis["max_loss"])

    prices, pnls = engine_strategies.timespread.payoff_curve(
        plan["legs"], max(plan["spot"] * 0.6, 0.01), plan["spot"] * 1.4,
        analysis["at_days"], CURVE_POINTS)

    source_meta = snapshot.get("meta", {})
    notes = list(source_meta.get("notes") or [])
    notes.append(plan["assumption"])

    payload = {
        "meta": envelope(
            schema=STRATEGY_PLAN,
            tool="optiondesk strategy",
            provider_used=source_meta.get("provider_used"),
            degraded=bool(source_meta.get("degraded")),
            degraded_reason=source_meta.get("degraded_reason"),
            inputs={"strategy": args.name, "snapshot": str(path),
                    "far_snapshot": str(far_path), "kind": args.kind,
                    "size": args.size},
            engine_version=engine["version"],
            notes=notes,
        ),
        "source_artifact": str(path),
        "strategy": plan["strategy"],
        "trade_type": plan["trade_type"],
        "underlying": snapshot["underlying"],
        "spot": plan["spot"],
        "expiry": plan["near_expiry"],
        "days_to_expiry": plan["near_days"],
        "size": args.size,
        "outlooks": [0],
        "outlook_labels": ["neutral (0)"],
        "when_to_use": playbook_when(args.name),
        "band": None,
        "legs": [leg.as_dict() for leg in plan["legs"]],
        "analysis": analysis,
        # A ratio diagonal is defined by the delta ratio it holds and the
        # giveback that ratio buys. Dropping them here would have written
        # a plan indistinguishable from a 1x1 with two contracts on one
        # leg, which is the thing the structure exists not to be.
        "delta_ratio": plan.get("delta_ratio"),
        "long_delta": plan.get("long_delta"),
        "short_delta": plan.get("short_delta"),
        "giveback": plan.get("giveback"),
        "probability": None,
        "net_greeks": None,
        "friction": None,
        "payoff_curve": {"prices": prices, "pnl": pnls},
    }
    validate(payload, SCHEMA_FILES[STRATEGY_PLAN])
    filename = "strategy_{}_{}_{}.json".format(
        str(snapshot["underlying"]).upper(), args.name, plan["near_expiry"])
    out = write_json(payload, filename, args.out_dir)

    return {
        "artifact": str(out),
        "strategy": plan["strategy"],
        "built": True,
        "degraded": bool(source_meta.get("degraded")),
        "degraded_reason": source_meta.get("degraded_reason"),
        "underlying": snapshot["underlying"],
        "near_expiry": plan["near_expiry"],
        "far_expiry": plan["far_expiry"],
        "near_days": plan["near_days"],
        "far_days": plan["far_days"],
        "spot": plan["spot"],
        "trade_type": analysis["trade_type"],
        "net_cash": analysis["net_cash"],
        "breakevens": analysis["breakevens"],
        "max_gain": analysis["max_gain"],
        "max_gain_at": analysis["max_gain_at"],
        "max_loss": analysis["max_loss"],
        "reward_risk": analysis["reward_risk"],
        "legs": payload["legs"],
        "assumption": plan["assumption"],
        "notes": notes,
    }


def playbook_when(name):
    """The playbook's own note on when a structure is the right one, or an
    empty string if the name is unknown.
    """
    from optiondesk import engine_bridge as bridge

    entry = bridge.strategies().PLAYBOOK.get(name, {})
    return entry.get("when_to_use", "")


def _jsonable(value):
    """Infinity is a fact about a trade, and JSON cannot hold it.

    Writing null would erase the distinction between an unbounded risk and
    an unknown one, and writing a big number would invent a floor that does
    not exist, so the string is used and the schema documents it.
    """
    if value == float("inf"):
        return "unlimited"
    if value == float("-inf"):
        return "unlimited"
    return value


def _net_greeks(engine, legs, spot, days, rate, dividend_yield):
    """Net position Greeks across the option legs, or None.

    Legs whose contract carries no implied volatility are skipped and
    counted, on the same principle as the ladder: a defaulted volatility
    would produce a complete and fictional risk profile.
    """
    if not days or days <= 0:
        return None
    t = days / 365.0
    keys = ("delta", "gamma", "vega", "theta", "rho", "vanna", "vomma",
            "charm")
    net = {key: 0.0 for key in keys}
    priced = skipped = 0
    for leg in legs:
        if leg.kind == "underlying":
            # One unit of the underlying is one delta by definition, and
            # carries no other Greek.
            net["delta"] += leg.side * leg.qty
            continue
        iv = (leg.ref or {}).get("iv")
        if not iv or iv <= 0:
            skipped += 1
            continue
        greeks = engine["all_greeks"](spot, leg.strike, t, float(iv),
                                      leg.kind, rate, dividend_yield)
        for key in keys:
            net[key] += leg.side * leg.qty * greeks[key]
        priced += 1
    net["legs_priced"] = priced
    net["legs_skipped_without_iv"] = skipped
    net["complete"] = skipped == 0
    if priced == 0 and any(leg.kind != "underlying" for leg in legs):
        # Not a delta-neutral position: a position nothing could be priced
        # for. Zeros here are indistinguishable from a real hedge, so every
        # Greek is None and only the counts survive.
        for key in keys:
            net[key] = None
    return net


def _curve_bounds(spot, band, strikes):
    """Draw the region a reader actually needs to see.

    Wide enough to show every strike in the structure and the whole
    expected move, plus room beyond for an unbounded leg to establish its
    slope. Not so wide that the interesting part is a few pixels: the
    bound is anchored on spot and on the structure, never on the extremes
    of a chain that lists strikes nobody trades.
    """
    span = spot * FALLBACK_SPAN
    if band:
        span = max(span, (band[1] - band[0]) * 1.5)
    if strikes:
        span = max(span, (max(strikes) - min(strikes)) * 1.2)
    lo = max(spot - span, 0.01)
    hi = spot + span
    return lo, hi


def run(args):
    """Build one named structure, or recommend one from the stated view, and
    write a plan artifact.
    """
    engine = engine_bridge.require()
    engine_strategies = engine_bridge.strategies()

    playbook = engine_strategies.PLAYBOOK

    if args.list_only:
        return {
            "strategies": [
                {
                    "name": name,
                    "trade_type": meta["trade_type"],
                    "outlooks": [int(o) for o in meta["outlooks"]],
                    "outlook_labels": [o.label for o in meta["outlooks"]],
                    "vol_view": meta["vol_view"],
                    "needs_underlying": meta["needs_underlying"],
                    "buildable": bool(meta["build"]
                                      or meta.get("build_two_expiry")),
                    "needs_two_expiries": bool(
                        meta.get("build_two_expiry")),
                    "when_to_use": meta["when_to_use"],
                }
                for name, meta in sorted(playbook.items())
            ],
        }

    if args.recommend is not None:
        ranked = engine_strategies.recommend(
            int(args.recommend), vol_view=args.vol_view,
            owns_underlying=args.owns_underlying,
            direction_known=not args.direction_unknown)
        return {
            "outlook": int(args.recommend),
            "vol_view": args.vol_view,
            "ranked": [
                {"strategy": name, "score": round(score, 3),
                 "trade_type": meta["trade_type"],
                 "buildable": meta["build"] is not None,
                 "when_to_use": meta["when_to_use"]}
                for name, score, meta in ranked
            ],
            "note": ("Ranking is a stated heuristic matching structures to a "
                     "view. It does not judge whether the view is right, and "
                     "it is not a recommendation to trade."),
        }

    if not args.name:
        raise ValueError("give a strategy name, or use --list or "
                         "--recommend OUTLOOK")

    path = args.snapshot or latest("chain_*.json", args.out_dir)
    if path is None:
        raise FileNotFoundError(
            "no chain snapshot given and none found. Run 'optiondesk chain "
            "SYMBOL' first, or pass --snapshot PATH.")
    snapshot = read_json(path)

    meta_entry = playbook.get(args.name, {})
    if meta_entry.get("build_two_expiry"):
        return _time_spread(args, engine, engine_strategies, snapshot, path)

    chain = engine_strategies.split_chain(snapshot)
    source_meta = snapshot.get("meta", {})
    kwargs = {"size": args.size}
    if playbook.get(args.name, {}).get("needs_underlying"):
        kwargs["underlying_entry"] = args.underlying_entry
    plan = engine_strategies.build(args.name, chain, **kwargs)
    if plan is None:
        return {
            "strategy": args.name,
            "built": False,
            "degraded": bool(source_meta.get("degraded")),
            "degraded_reason": source_meta.get("degraded_reason"),
            "reason": ("no viable structure on this chain: the strikes, "
                       "quotes or expected move did not admit one. Try "
                       "another expiry or another strategy."),
            "source_artifact": str(path),
        }

    spot = plan["spot"]
    days = plan["days_to_expiry"]
    rate = float(snapshot.get("risk_free_rate", 0.04))
    dividend_yield = float(snapshot.get("dividend_yield", 0.0))
    iv = engine_strategies.chain_iv(chain, spot)

    probability = None
    pop = engine_strategies.probability_of_profit(plan["legs"], spot, iv, days)
    tails = engine_strategies.tail_metrics(plan["legs"], spot, iv, days)
    if pop is not None or tails is not None:
        probability = {
            "profit": pop,
            "loss": tails["p_loss"] if tails else None,
            "expected_pnl": tails["expected_pnl"] if tails else None,
            "expected_loss": tails["expected_loss"] if tails else None,
            "model": ("lognormal settlement at the at-the-money implied "
                      "volatility of {:.4f}, no drift".format(iv)
                      if iv else "unavailable"),
        }

    friction = engine_strategies.plan_friction(
        plan["legs"], net_cash=plan["analysis"]["net_cash"])
    net_greeks = _net_greeks(engine, plan["legs"], spot, days, rate,
                             dividend_yield)

    strikes = [leg.strike for leg in plan["legs"] if leg.strike]
    lo, hi = _curve_bounds(spot, plan["band"], strikes)
    prices, pnls = engine_strategies.payoff_curve(plan["legs"], lo, hi,
                                                  CURVE_POINTS)

    analysis = dict(plan["analysis"])
    analysis["max_gain"] = _jsonable(analysis["max_gain"])
    analysis["max_loss"] = _jsonable(analysis["max_loss"])

    source_meta = snapshot.get("meta", {})
    notes = list(source_meta.get("notes") or [])
    if net_greeks and net_greeks["legs_skipped_without_iv"]:
        notes.append("{} leg(s) had no implied volatility, so the net Greeks "
                     "exclude them".format(
                         net_greeks["legs_skipped_without_iv"]))
    if friction["verdict"] in ("thin", "untradeable"):
        notes.append("friction verdict {}: {}".format(friction["verdict"],
                                                      friction["reason"]))

    payload = {
        "meta": envelope(
            schema=STRATEGY_PLAN,
            tool="optiondesk strategy",
            provider_used=source_meta.get("provider_used"),
            degraded=bool(source_meta.get("degraded")),
            degraded_reason=source_meta.get("degraded_reason"),
            inputs={"strategy": args.name, "snapshot": str(path),
                    "size": args.size},
            engine_version=engine["version"],
            notes=notes,
        ),
        "source_artifact": str(path),
        "strategy": plan["strategy"],
        "trade_type": plan["trade_type"],
        "underlying": snapshot["underlying"],
        "spot": spot,
        "expiry": plan["expiry"],
        "days_to_expiry": days,
        "size": args.size,
        "outlooks": plan["outlooks"],
        "outlook_labels": plan["outlook_labels"],
        "when_to_use": plan["when_to_use"],
        "band": plan["band"],
        "legs": [leg.as_dict() for leg in plan["legs"]],
        "analysis": analysis,
        "probability": probability,
        "net_greeks": net_greeks,
        "friction": friction,
        "payoff_curve": {"prices": prices, "pnl": pnls},
    }
    validate(payload, SCHEMA_FILES[STRATEGY_PLAN])
    filename = "strategy_{}_{}_{}.json".format(
        str(snapshot["underlying"]).upper(), args.name, snapshot["expiry"])
    out = write_json(payload, filename, args.out_dir)

    return {
        "artifact": str(out),
        "strategy": plan["strategy"],
        "built": True,
        "degraded": bool(source_meta.get("degraded")),
        "degraded_reason": source_meta.get("degraded_reason"),
        "underlying": snapshot["underlying"],
        "expiry": plan["expiry"],
        "spot": spot,
        "trade_type": analysis["trade_type"],
        "net_cash": analysis["net_cash"],
        "breakevens": analysis["breakevens"],
        "max_gain": analysis["max_gain"],
        "max_loss": analysis["max_loss"],
        "reward_risk": analysis["reward_risk"],
        "probability_of_profit": probability["profit"] if probability else None,
        "expected_pnl": probability["expected_pnl"] if probability else None,
        "friction_verdict": friction["verdict"],
        "friction_reason": friction["reason"],
        "net_delta": net_greeks["delta"] if net_greeks else None,
        "net_theta": net_greeks["theta"] if net_greeks else None,
        "net_vega": net_greeks["vega"] if net_greeks else None,
        "net_greeks_complete": (net_greeks["complete"] if net_greeks
                                else None),
        "legs": payload["legs"],
        "notes": notes,
    }


def main(argv=None):
    """Parse argv for this command alone and run it, so the command works when
    invoked directly as well as through the dispatcher.
    """
    parser = add_arguments(argparse.ArgumentParser(
        prog="optiondesk strategy", description=__doc__.splitlines()[0]))
    args = parser.parse_args(argv)
    print(json.dumps(run(args), indent=1, default=str))
    return 0
