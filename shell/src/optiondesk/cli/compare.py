"""optiondesk compare: every structure from one chain, side by side.

Builds each buildable strategy from the same snapshot, scores them on the
same basis, and orders the ones that can be ranked. The ordering criterion
is model expected profit per unit of capital at risk, and every component of
it is in the output so the order can be disagreed with.

The leader is not advice. Read the caveat: expectations come from a single
at-the-money volatility while the market prices every strike differently, so
a positive number here is largely a measurement of that gap.
"""

import argparse
import json

from pathlib import Path

from optiondesk import engine_bridge
from optiondesk.artifacts import (
    artifact_dir,
    envelope,
    latest,
    read_json,
    write_json,
)
from optiondesk.cli import strategy as strategy_cmd
from optiondesk.contracts import SCHEMA_FILES, STRATEGY_COMPARISON, validate


class _PlanArgs:
    """The arguments one strategy build needs, without argparse."""

    def __init__(self, name, snapshot, size, out_dir, far_snapshot=None,
                 kind="call", offset=0.03):
        self.name = name
        self.snapshot = snapshot
        self.size = size
        self.underlying_entry = None
        self.out_dir = out_dir
        self.list_only = False
        self.recommend = None
        self.vol_view = "neutral"
        self.owns_underlying = False
        self.direction_unknown = False
        # Time spreads need a second expiry and a side. strategy resolves
        # the far snapshot itself when it is not named.
        self.far_snapshot = far_snapshot
        self.kind = kind
        self.offset = offset


def add_arguments(parser):
    """Register comparison options: which snapshot, position size, whether to
    include the underlying, whether to rebuild plans rather than reuse them,
    and output directory.
    """
    parser.add_argument("--snapshot", default=None,
                        help="chain snapshot path. Default: most recent")
    parser.add_argument("--size", type=float, default=1.0,
                        help="contracts per leg")
    parser.add_argument("--include-underlying", action="store_true",
                        dest="include_underlying",
                        help="include structures that require holding the "
                             "underlying")
    parser.add_argument("--far-snapshot", default=None, dest="far_snapshot",
                        help="the later expiry used by the calendar and the "
                             "diagonal. Omit and the nearest later chain on "
                             "disk for this underlying is used")
    parser.add_argument("--rebuild", action="store_true",
                        help="rebuild every structure even when a plan for "
                             "it already exists for this chain")
    parser.add_argument("--out-dir", default=None,
                        help="artifact directory override")
    return parser


def run(args):
    """Build every buildable structure from one snapshot, rank them under
    stated assumptions and write a comparison artifact.
    """
    engine = engine_bridge.require()
    playbook = engine_bridge.strategies().PLAYBOOK
    analytics = engine_bridge.analytics()

    path = args.snapshot or latest("chain_*.json", args.out_dir)
    if path is None:
        raise FileNotFoundError(
            "no chain snapshot given and none found. Run 'optiondesk chain "
            "SYMBOL' first, or pass --snapshot PATH.")
    snapshot = read_json(path)

    plans = []
    failed = []
    reused = 0
    existing = {}
    if not args.rebuild:
        # Reuse plans already built from this exact snapshot. The flag was
        # previously declared and never read, so every run rebuilt
        # everything and the flag documented a behaviour that did not
        # exist.
        directory = Path(args.out_dir) if args.out_dir else artifact_dir()
        for candidate in directory.glob("strategy_{}_*.json".format(
                str(snapshot["underlying"]).upper())):
            try:
                plan = read_json(candidate)
            except (ValueError, OSError):
                continue
            if not isinstance(plan, dict):
                continue
            if plan.get("source_artifact") == str(path):
                existing[plan.get("strategy")] = plan

    for name, meta in sorted(playbook.items()):
        # A structure with no single-expiry builder is a time spread. It
        # was skipped outright, so a comparison could never hold a calendar
        # or a diagonal even with both expiries on disk, and the artifact
        # said only "needs two expiries" as though the data were missing.
        # strategy already resolves the far chain itself, so the build is
        # the same call with the extra arguments.
        if meta["build"] is None:
            try:
                result = strategy_cmd.run(_PlanArgs(
                    name, str(path), args.size, args.out_dir,
                    far_snapshot=getattr(args, "far_snapshot", None)))
            except FileNotFoundError as exc:
                failed.append({"strategy": name, "reason": str(exc)})
                continue
            except Exception as exc:
                failed.append({"strategy": name,
                               "reason": "{}: {}".format(
                                   type(exc).__name__, exc)})
                continue
            if not result.get("built"):
                failed.append({"strategy": name,
                               "reason": result.get("reason",
                                                    "no viable structure")})
                continue
            plans.append(read_json(result["artifact"]))
            continue
        if meta["needs_underlying"] and not args.include_underlying:
            failed.append({"strategy": name,
                           "reason": "requires holding the underlying; pass "
                                     "--include-underlying"})
            continue
        if name in existing:
            plans.append(existing[name])
            reused += 1
            continue
        try:
            result = strategy_cmd.run(_PlanArgs(name, str(path), args.size,
                                                args.out_dir))
        except Exception as exc:
            # One structure that cannot be priced must not take the other
            # nine with it. A chain whose calls have no two-sided quote
            # killed the entire comparison while long_put built fine from
            # the same data.
            failed.append({"strategy": name,
                           "reason": "{}: {}".format(type(exc).__name__,
                                                     exc)})
            continue
        if not result.get("built"):
            failed.append({"strategy": name,
                           "reason": result.get("reason", "no viable "
                                                          "structure")})
            continue
        plans.append(read_json(result["artifact"]))

    comparison = analytics.rank_strategies(plans)

    source_meta = snapshot.get("meta", {})
    notes = list(source_meta.get("notes") or [])
    for entry in failed:
        notes.append("{} not compared: {}".format(entry["strategy"],
                                                  entry["reason"]))

    payload = {
        "meta": envelope(
            schema=STRATEGY_COMPARISON,
            tool="optiondesk compare",
            provider_used=source_meta.get("provider_used"),
            degraded=bool(source_meta.get("degraded")),
            degraded_reason=source_meta.get("degraded_reason"),
            inputs={"snapshot": str(path), "size": args.size},
            engine_version=engine["version"],
            notes=notes,
        ),
        "underlying": snapshot["underlying"],
        "expiry": snapshot.get("expiry"),
        "spot": snapshot.get("spot"),
        "criterion": comparison["criterion"],
        "caveat": comparison["caveat"],
        "rankable_count": comparison["rankable_count"],
        "excluded_count": comparison["excluded_count"],
        "margin_over_runner_up": comparison["margin_over_runner_up"],
        "leader": comparison["leader"],
        "rows": comparison["rows"],
        "ranked": comparison["ranked"],
        # Persisted, not only printed. The stdout summary carried this and
        # the artifact did not, so the dashboard could show twelve
        # structures out of twenty-one with nothing on the page saying which
        # five were missing or why.
        "not_compared": failed,
    }
    validate(payload, SCHEMA_FILES[STRATEGY_COMPARISON])
    filename = "comparison_{}_{}.json".format(
        str(snapshot["underlying"]).upper(), snapshot["expiry"])
    out = write_json(payload, filename, args.out_dir)

    leader = comparison["leader"]
    return {
        "artifact": str(out),
        "underlying": snapshot["underlying"],
        "expiry": snapshot.get("expiry"),
        "degraded": bool(source_meta.get("degraded")),
        "degraded_reason": source_meta.get("degraded_reason"),
        "compared": len(plans),
        "reused_existing_plans": reused,
        "rankable": comparison["rankable_count"],
        "excluded": comparison["excluded_count"],
        "leader": ({"strategy": leader["strategy"],
                    "expected_return_on_risk":
                        leader["expected_return_on_risk"],
                    "probability_of_profit":
                        leader["probability_of_profit"],
                    "capital_at_risk": leader["capital_at_risk"],
                    "friction": leader["friction_verdict"]}
                   if leader else None),
        "margin_over_runner_up": comparison["margin_over_runner_up"],
        "criterion": comparison["criterion"],
        "caveat": comparison["caveat"],
        "not_compared": failed,
    }


def main(argv=None):
    """Parse argv for this command alone and run it, so the command works when
    invoked directly as well as through the dispatcher.
    """
    parser = add_arguments(argparse.ArgumentParser(
        prog="optiondesk compare", description=__doc__.splitlines()[0]))
    args = parser.parse_args(argv)
    print(json.dumps(run(args), indent=1, default=str))
    return 0
