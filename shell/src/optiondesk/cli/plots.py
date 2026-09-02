"""Create chat-ready PNG plots from an option-chain snapshot."""

import argparse
import json
import os
from pathlib import Path
from types import SimpleNamespace

from optiondesk import engine_bridge
from optiondesk.artifacts import archive_existing, artifact_dir, read_json
from optiondesk.cli import chain as chain_cmd
from optiondesk.cli import exposure as exposure_cmd
from optiondesk.cli import greeks as greeks_cmd
from optiondesk.plotting import greeks_png, market_png


def add_arguments(parser):
    parser.add_argument("symbol", help="underlying ticker, for example SPY")
    parser.add_argument("--snapshot", default=None,
                        help="existing chain snapshot path")
    parser.add_argument("--from-file", dest="source_path", default=None,
                        help="CSV or JSON chain snapshot to import")
    parser.add_argument("--data-source", default=None,
                        help="name of the user-supplied data source")
    parser.add_argument("--accept-data-rights", action="store_true",
                        dest="rights_confirmed",
                        help="confirm that you can send this data for private "
                             "analysis")
    parser.add_argument("--expiry", default=None,
                        help="expiry as YYYY-MM-DD. Default: nearest listed")
    parser.add_argument("--rate", type=float, default=None)
    parser.add_argument("--dividend-yield", type=float, default=None,
                        dest="dividend_yield")
    parser.add_argument("--band", type=float, default=0.15,
                        help="fraction around spot shown in plots; 0 shows all")
    parser.add_argument("--out-dir", default=None,
                        help="artifact directory override")
    return parser


def _write_png(data, filename, directory=None):
    target_dir = Path(directory) if directory else artifact_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / filename
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(data)
    if path.exists() and path.read_bytes() != data:
        archive_existing(path)
    os.replace(temporary, path)
    return path


def _chain_args(args):
    return SimpleNamespace(
        symbol=args.symbol,
        expiry=args.expiry,
        provider=None,
        source_path=getattr(args, "source_path", None),
        from_file=getattr(args, "source_path", None),
        source_text=getattr(args, "source_text", None),
        source_data=getattr(args, "source_data", None),
        source_format=getattr(args, "source_format", None),
        data_source=getattr(args, "data_source", None),
        rights_confirmed=getattr(args, "rights_confirmed", False),
        rate=args.rate,
        dividend_yield=args.dividend_yield,
        out_dir=args.out_dir,
    )


def _current_artifact(path, source_path):
    """Read an analytic artifact when it is at least as new as its chain."""
    if not path.is_file():
        return None
    try:
        if path.stat().st_mtime < Path(source_path).stat().st_mtime:
            return None
        return read_json(path)
    except (OSError, ValueError):
        return None


def run(args):
    """Fetch or read a chain, calculate available analytics, and write PNGs."""
    chain_summary = None
    snapshot_path = args.snapshot
    if snapshot_path is None:
        chain_summary = chain_cmd.run(_chain_args(args))
        snapshot_path = chain_summary["artifact"]

    chain = read_json(snapshot_path)
    symbol = str(chain.get("underlying") or args.symbol).upper()
    expiry = str(chain.get("expiry"))
    target = args.out_dir
    target_dir = Path(target) if target else artifact_dir()
    ladder_path = target_dir / "greeks_{}_{}.json".format(symbol, expiry)
    exposure_path = target_dir / "exposure_{}_{}.json".format(symbol, expiry)
    ladder = _current_artifact(ladder_path, snapshot_path)
    exposure = _current_artifact(exposure_path, snapshot_path)
    analytics_errors = []

    if engine_bridge.AVAILABLE:
        if ladder is None:
            try:
                greeks_summary = greeks_cmd.run(SimpleNamespace(
                    snapshot=str(snapshot_path), band=args.band, type="both",
                    out_dir=target))
                ladder = read_json(greeks_summary["artifact"])
            except (FileNotFoundError, ImportError, RuntimeError,
                    ValueError) as exc:
                analytics_errors.append("Greeks {}: {}".format(
                    type(exc).__name__, exc))
        if exposure is None:
            try:
                exposure_summary = exposure_cmd.run(SimpleNamespace(
                    snapshot=str(snapshot_path), multiplier=100.0,
                    out_dir=target))
                exposure = read_json(exposure_summary["artifact"])
            except (FileNotFoundError, ImportError, RuntimeError,
                    ValueError) as exc:
                analytics_errors.append("Positioning {}: {}".format(
                    type(exc).__name__, exc))
    else:
        missing = []
        if ladder is None:
            missing.append("Greek")
        if exposure is None:
            missing.append("positioning")
        if missing:
            analytics_errors.append(
                "{} plots are unavailable. {}".format(
                    " and ".join(missing), engine_bridge.MISSING_MESSAGE))

    user_supplied = bool((chain.get("meta") or {}).get("inputs", {}).get(
        "user_supplied"))
    footer = None
    if user_supplied:
        footer = (
            "USER-SUPPLIED DATA / PRIVATE RESEARCH / NOT INVESTMENT ADVICE "
            "/ DO NOT USE FOR ORDERS")

    market_path = _write_png(
        market_png(chain, exposure, band=args.band, footer=footer),
        "plots_{}_{}_market.png".format(symbol, expiry), target)
    paths = [str(market_path)]
    if ladder and ladder.get("rows"):
        greek_path = _write_png(
            greeks_png(ladder, footer=footer),
            "plots_{}_{}_greeks.png".format(symbol, expiry), target)
        paths.append(str(greek_path))

    meta = chain.get("meta") or {}
    reasons = [str(meta.get("degraded_reason"))] if meta.get(
        "degraded_reason") else []
    reasons.extend(analytics_errors)
    return {
        "plots": paths,
        "source_artifact": str(snapshot_path),
        "underlying": symbol,
        "expiry": expiry,
        "spot": chain.get("spot"),
        "spot_asof": chain.get("spot_asof"),
        "provider_used": meta.get("provider_used"),
        "data_source": chain.get("data_source"),
        "user_supplied": user_supplied,
        "degraded": bool(meta.get("degraded")) or bool(analytics_errors),
        "degraded_reason": "; ".join(reasons) or None,
        "analytics_included": {
            "positioning": bool(exposure),
            "greeks": bool(ladder and ladder.get("rows")),
        },
        "chain_retrieved": chain_summary is not None,
    }


def main(argv=None):
    parser = add_arguments(argparse.ArgumentParser(
        prog="optiondesk plots", description=__doc__.splitlines()[0]))
    print(json.dumps(run(parser.parse_args(argv)), indent=1))
    return 0
