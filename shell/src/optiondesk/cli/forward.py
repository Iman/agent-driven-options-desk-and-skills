"""optiondesk forward: a paper ledger of positions recorded before the fact.

Four verbs.

  open    record a structure from a plan artifact, with its legs and entry
          marks fixed at that moment, and an optional thesis in your own
          words
  mark    re-mark every open position against the newest chain snapshot for
          its underlying and expiry
  close   settle a position, either at a supplied price or at the newest
          spot, and stop marking it
  status  the ledger, with the running result

Why this exists next to the backtest: a backtest can be tuned until it
looks good, because the outcome is already in the data. A forward test
cannot. The entry, the strikes and the mark are written down before the
marking data exists, so what comes back is at least an honest measurement
of the rule as it was actually stated.

It remains paper. Entry and marks are snapshot mid quotes, and a real entry
would have crossed the spread on every leg.
"""

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from optiondesk import engine_bridge
from optiondesk.artifacts import (
    artifact_dir,
    envelope,
    latest,
    read_json,
    write_json,
)
from optiondesk.contracts import FORWARD_LEDGER, SCHEMA_FILES, validate

LEDGER = "forward_ledger.json"


def add_arguments(parser):
    parser.add_argument("action", choices=("open", "mark", "close", "status"),
                        help="what to do with the ledger")
    parser.add_argument("--plan", default=None,
                        help="strategy plan artifact to open a position from")
    parser.add_argument("--strategy", default=None,
                        help="strategy name, to find the newest plan for it")
    parser.add_argument("--underlying", default=None,
                        help="restrict to one underlying")
    parser.add_argument("--id", default=None, dest="position_id",
                        help="position identifier, for close")
    parser.add_argument("--price", type=float, default=None,
                        help="settlement price for close. Default: the "
                             "newest spot on file")
    parser.add_argument("--thesis", default=None,
                        help="why you are taking this, in your own words")
    parser.add_argument("--out-dir", default=None)
    return parser


def _directory(args):
    return Path(args.out_dir) if args.out_dir else artifact_dir()


def _load(directory):
    path = Path(directory) / LEDGER
    if not path.exists():
        return {"positions": []}
    try:
        return read_json(path)
    except (ValueError, OSError):
        return {"positions": []}


def _save(ledger, directory, engine_version, notes=None):
    positions = ledger["positions"]
    open_positions = [p for p in positions if p["status"] == "open"]
    closed = [p for p in positions if p["status"] == "closed"]
    settled = [p["settlement"]["profit"] for p in closed
               if p.get("settlement")]
    payload = {
        "meta": envelope(
            schema=FORWARD_LEDGER,
            tool="optiondesk forward",
            provider_used=None,
            inputs={},
            engine_version=engine_version,
            notes=notes or [],
        ),
        "positions": positions,
        "summary": {
            "open": len(open_positions),
            "closed": len(closed),
            "settled_profit": sum(settled) if settled else 0.0,
            "wins": sum(1 for value in settled if value > 0),
            "losses": sum(1 for value in settled if value < 0),
            "note": ("Paper results from mid quotes. Not fills, and not a "
                     "track record."),
        },
    }
    validate(payload, SCHEMA_FILES[FORWARD_LEDGER])
    return write_json(payload, LEDGER, directory)


def _newest_chain(directory, underlying, expiry):
    """The newest snapshot for one underlying and expiry, or None."""
    best = None
    for path in Path(directory).glob("chain_{}_*.json".format(
            (underlying or "").upper())):
        try:
            snapshot = read_json(path)
        except (ValueError, OSError):
            continue
        if expiry and snapshot.get("expiry") != expiry:
            continue
        if best is None or path.stat().st_mtime > best[1]:
            best = (snapshot, path.stat().st_mtime, str(path))
    return (best[0], best[2]) if best else (None, None)


def run(args):
    engine = engine_bridge.require()
    forward = engine_bridge.backtest()
    strategies = engine_bridge.strategies()
    directory = _directory(args)
    ledger = _load(directory)

    if args.action == "status":
        return _status(ledger, args)

    if args.action == "open":
        return _open(ledger, args, directory, engine)

    if args.action == "mark":
        return _mark(ledger, args, directory, forward, engine)

    return _close(ledger, args, directory, forward, strategies, engine)


def _open(ledger, args, directory, engine):
    path = args.plan
    if path is None and args.strategy:
        pattern = "strategy_{}_{}_*.json".format(
            (args.underlying or "*").upper(), args.strategy)
        path = latest(pattern, args.out_dir)
    if path is None:
        path = latest("strategy_*.json", args.out_dir)
    if path is None:
        raise FileNotFoundError(
            "no strategy plan given and none found. Build one with "
            "'optiondesk strategy NAME', or pass --plan PATH.")
    plan = read_json(path)

    entry_value = 0.0
    for leg in plan["legs"]:
        sign = 1 if leg["side"] == "long" else -1
        entry_value += sign * float(leg["qty"]) * float(leg["price"])

    position = {
        "id": uuid.uuid4().hex[:12],
        "strategy": plan["strategy"],
        "underlying": plan["underlying"],
        "expiry": plan.get("expiry"),
        "opened_utc": datetime.now(timezone.utc).isoformat(
            timespec="seconds"),
        "closed_utc": None,
        "status": "open",
        "size": plan.get("size", 1.0),
        "entry_spot": plan["spot"],
        "entry_value": entry_value,
        "trade_type": plan.get("trade_type"),
        "source_plan": str(path),
        "thesis": args.thesis,
        "legs": plan["legs"],
        "marks": [],
        "settlement": None,
    }
    ledger["positions"].append(position)
    out = _save(ledger, directory, engine["version"])
    return {
        "action": "open",
        "ledger": str(out),
        "id": position["id"],
        "strategy": position["strategy"],
        "underlying": position["underlying"],
        "expiry": position["expiry"],
        "entry_spot": position["entry_spot"],
        "entry_value": entry_value,
        "legs": len(position["legs"]),
        "thesis": position["thesis"],
        "note": ("Recorded. Mark it later with 'optiondesk forward mark' "
                 "once a newer chain snapshot exists. Entry marks are mid "
                 "quotes, not fills."),
    }


def _mark(ledger, args, directory, forward, engine):
    marked = []
    unmarkable = []
    for position in ledger["positions"]:
        if position["status"] != "open":
            continue
        if args.underlying and position["underlying"].upper() != \
                args.underlying.upper():
            continue
        snapshot, snapshot_path = _newest_chain(directory,
                                                position["underlying"],
                                                position["expiry"])
        if snapshot is None:
            unmarkable.append({"id": position["id"],
                               "reason": "no chain snapshot on file for {} "
                                         "{}".format(position["underlying"],
                                                     position["expiry"])})
            continue
        result = forward.mark_position(position, snapshot)
        result["snapshot"] = snapshot_path
        if not result["markable"]:
            unmarkable.append({"id": position["id"],
                               "reason": "; ".join(result["problems"])})
            position["marks"].append(result)
            continue
        position["marks"].append(result)
        marked.append({
            "id": position["id"],
            "strategy": position["strategy"],
            "profit": result["profit"],
            "spot": result["spot"],
            "underlying_move": result["underlying_move"],
            "stale_marks": result["stale_marks"],
        })

    notes = []
    if unmarkable:
        notes.append("{} position(s) could not be marked".format(
            len(unmarkable)))
    out = _save(ledger, directory, engine["version"], notes)
    return {
        "action": "mark",
        "ledger": str(out),
        "marked": marked,
        "unmarkable": unmarkable,
        "open_profit": sum(m["profit"] for m in marked),
        "note": ("Marks are snapshot mid quotes. A position with any leg "
                 "missing from the newer chain is reported unmarkable "
                 "rather than marked at zero."),
    }


def _close(ledger, args, directory, forward, strategies, engine):
    if not args.position_id:
        raise ValueError("closing needs --id. Run 'optiondesk forward "
                         "status' to list positions.")
    matches = [p for p in ledger["positions"]
               if p["id"] == args.position_id and p["status"] == "open"]
    if not matches:
        raise ValueError("no open position with id {}".format(
            args.position_id))
    position = matches[0]

    price = args.price
    if price is None:
        snapshot, _ = _newest_chain(directory, position["underlying"],
                                    position["expiry"])
        if snapshot is None:
            raise ValueError(
                "no price given and no chain snapshot on file for {}. Pass "
                "--price.".format(position["underlying"]))
        price = snapshot["spot"]

    def build(legs):
        return [strategies.Leg(
            leg["kind"], 1 if leg["side"] == "long" else -1,
            float(leg["price"]), strike=leg.get("strike"),
            qty=float(leg["qty"])) for leg in legs]

    settlement = forward.settle_position(position, price,
                                         strategies.pnl_at_expiry, build)
    position["settlement"] = settlement
    position["status"] = "closed"
    position["closed_utc"] = datetime.now(timezone.utc).isoformat(
        timespec="seconds")
    out = _save(ledger, directory, engine["version"])
    return {
        "action": "close",
        "ledger": str(out),
        "id": position["id"],
        "strategy": position["strategy"],
        "settlement_price": settlement["settlement_price"],
        "profit": settlement["profit"],
        "underlying_move": settlement["underlying_move"],
        "held_from": position["opened_utc"],
        "held_to": position["closed_utc"],
        "note": settlement["note"],
    }


def _status(ledger, args):
    rows = []
    for position in ledger["positions"]:
        if args.underlying and position["underlying"].upper() != \
                args.underlying.upper():
            continue
        last_mark = position["marks"][-1] if position["marks"] else None
        rows.append({
            "id": position["id"],
            "status": position["status"],
            "strategy": position["strategy"],
            "underlying": position["underlying"],
            "expiry": position["expiry"],
            "opened_utc": position["opened_utc"],
            "entry_spot": position["entry_spot"],
            "marks": len(position["marks"]),
            "last_mark_profit": (last_mark.get("profit")
                                 if last_mark and last_mark.get("markable")
                                 else None),
            "settled_profit": (position["settlement"]["profit"]
                               if position.get("settlement") else None),
            "thesis": position.get("thesis"),
        })
    closed = [r for r in rows if r["status"] == "closed"]
    settled = [r["settled_profit"] for r in closed
               if r["settled_profit"] is not None]
    return {
        "action": "status",
        "positions": rows,
        "open": sum(1 for r in rows if r["status"] == "open"),
        "closed": len(closed),
        "settled_profit": sum(settled) if settled else 0.0,
        "note": ("Paper ledger from mid quotes. Not fills and not a track "
                 "record."),
    }


def main(argv=None):
    parser = add_arguments(argparse.ArgumentParser(
        prog="optiondesk forward", description=__doc__.splitlines()[0]))
    args = parser.parse_args(argv)
    print(json.dumps(run(args), indent=1, default=str))
    return 0
