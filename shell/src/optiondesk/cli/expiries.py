"""optiondesk expiries: what is listed, and what is already on disk.

Answers the first question anyone has in front of an option desk: which
expiries exist for this underlying, and which of them have I already pulled.
It reaches the provider for the listing and reads the artifact directory for
the rest, so the output is a menu rather than a guess.
"""

import argparse
import json
from datetime import datetime, timezone

from optiondesk.artifacts import artifact_dir, read_json
from optiondesk.providers import CAP_OPTION_CHAIN, resolve


def add_arguments(parser):
    parser.add_argument("symbol", nargs="?", default=None,
                        help="underlying ticker. Omit to list only what is "
                             "already on disk, with no network access")
    parser.add_argument("--provider", default=None,
                        help="force a provider instead of the registry order")
    parser.add_argument("--out-dir", default=None,
                        help="artifact directory to inspect")
    return parser


def on_disk(directory=None):
    """Every underlying and expiry already pulled, and what exists for it."""
    target = artifact_dir(directory)
    found = {}
    if not target.exists():
        return found
    for path in sorted(target.glob("*.json")):
        kind = path.name.split("_")[0]
        if kind not in ("chain", "greeks", "exposure", "strategy"):
            continue
        try:
            payload = read_json(path)
        except (ValueError, OSError):
            continue
        if not isinstance(payload, dict):
            # Parses, but is not an artifact. Skipped like an unreadable
            # file rather than reaching .get() and raising.
            continue
        underlying = payload.get("underlying")
        expiry = payload.get("expiry")
        if not underlying:
            continue
        entry = found.setdefault((underlying, expiry), {
            "underlying": underlying, "expiry": expiry, "artifacts": {},
            "strategies": [], "spot": payload.get("spot"),
            "generated_utc": payload.get("meta", {}).get("generated_utc"),
        })
        entry["artifacts"][kind] = str(path)
        if kind == "strategy" and payload.get("strategy"):
            entry["strategies"].append(payload["strategy"])
    return found


def run(args):
    directory = args.out_dir
    local = on_disk(directory)

    if not args.symbol:
        return {
            "artifact_dir": str(artifact_dir(directory)),
            "on_disk": [
                {"underlying": v["underlying"], "expiry": v["expiry"],
                 "spot": v["spot"], "have": sorted(v["artifacts"]),
                 "strategies": sorted(v["strategies"])}
                for v in sorted(local.values(),
                                key=lambda e: (e["underlying"] or "",
                                               e["expiry"] or ""))
            ],
            "hint": ("Pass a symbol to see every expiry the provider lists, "
                     "for example: optiondesk expiries QQQ"),
        }

    symbol = args.symbol.upper()
    provider, choice = resolve(CAP_OPTION_CHAIN, args.provider)
    listed = provider.expiries(symbol)
    now = datetime.now(timezone.utc)

    have = {expiry for (underlying, expiry) in local
            if underlying and underlying.upper() == symbol}

    rows = []
    for expiry in listed:
        try:
            expiry_dt = datetime.strptime(expiry, "%Y-%m-%d").replace(
                hour=21, tzinfo=timezone.utc)
            days = round((expiry_dt - now).total_seconds() / 86400.0, 2)
        except ValueError:
            days = None
        rows.append({"expiry": expiry, "days_to_expiry": days,
                     "on_disk": expiry in have})

    return {
        "underlying": symbol,
        "provider_used": provider.name,
        "listed": len(rows),
        "already_pulled": sorted(have),
        "expiries": rows,
        "next": ("optiondesk chain {} --expiry {}".format(
            symbol, rows[0]["expiry"]) if rows else None),
    }


def main(argv=None):
    parser = add_arguments(argparse.ArgumentParser(
        prog="optiondesk expiries", description=__doc__.splitlines()[0]))
    args = parser.parse_args(argv)
    print(json.dumps(run(args), indent=1, default=str))
    return 0
