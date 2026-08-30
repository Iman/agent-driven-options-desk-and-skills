"""optiondesk command dispatcher."""

import argparse
import json
import sys

from optiondesk import __version__, engine_bridge
from optiondesk.artifacts import DISCLAIMER, artifact_dir
from optiondesk.cli import backtest as backtest_cmd
from optiondesk.cli import chain as chain_cmd
from optiondesk.cli import forward as forward_cmd
from optiondesk.cli import greeks as greeks_cmd
from optiondesk.cli import keys as keys_cmd
from optiondesk.cli import compare as compare_cmd
from optiondesk.cli import exposure as exposure_cmd
from optiondesk.cli import expiries as expiries_cmd
from optiondesk.cli import simulate as simulate_cmd
from optiondesk.cli import strategy as strategy_cmd
from optiondesk.config import configured_providers
from optiondesk.providers import describe_all


def _doctor(_args):
    """Report what is installed, what is reachable, and what is missing."""
    return {
        "shell_version": __version__,
        "artifact_dir": str(artifact_dir()),
        "engine": engine_bridge.status(),
        "providers": describe_all(),
        "credentials": configured_providers(),
        "disclaimer": DISCLAIMER,
    }


def build_parser():
    """Assemble the top level parser by asking each command module to register
    its own arguments.
    """
    parser = argparse.ArgumentParser(
        prog="optiondesk",
        description="Option desk: chain retrieval, analytics, artifacts. "
                    "Research software, not investment advice. See "
                    "DISCLAIMER.md.")
    parser.add_argument("--version", action="version",
                        version="optiondesk {}".format(__version__))
    sub = parser.add_subparsers(dest="command", required=True)

    chain_cmd.add_arguments(sub.add_parser(
        "chain", help="retrieve an option chain snapshot"))
    greeks_cmd.add_arguments(sub.add_parser(
        "greeks", help="full Greek ladder from a snapshot"))
    strategy_cmd.add_arguments(sub.add_parser(
        "strategy", help="build a multi-leg strategy from a snapshot"))
    exposure_cmd.add_arguments(sub.add_parser(
        "exposure", help="dealer gamma, walls, max pain and smile geometry"))
    expiries_cmd.add_arguments(sub.add_parser(
        "expiries", help="list available expiries and what is on disk"))
    compare_cmd.add_arguments(sub.add_parser(
        "compare", help="every structure side by side, ranked"))
    simulate_cmd.add_arguments(sub.add_parser(
        "simulate", help="GARCH-t posterior, forward paths and tail risk"))
    backtest_cmd.add_arguments(sub.add_parser(
        "backtest", help="run a structure across real history, modelled "
                         "premiums"))
    forward_cmd.add_arguments(sub.add_parser(
        "forward", help="paper ledger: open, mark, close, status"))
    keys_cmd.add_arguments(sub.add_parser(
        "keys", help="see, set or locate provider credentials"))
    sub.add_parser("doctor",
                   help="report engine, provider and credential status")

    dash = sub.add_parser("dashboard", help="serve the local dashboard")
    dash.add_argument("--host", default="127.0.0.1")
    dash.add_argument("--port", type=int, default=8787)
    dash.add_argument("--out-dir", default=None,
                      help="artifact directory to read")
    return parser


def _dashboard(args):
    from optiondesk.dashboard.app import serve
    serve(args.host, args.port, args.out_dir)
    return {"served": "http://{}:{}".format(args.host, args.port)}


HANDLERS = {
    "chain": chain_cmd.run,
    "greeks": greeks_cmd.run,
    "strategy": strategy_cmd.run,
    "exposure": exposure_cmd.run,
    "expiries": expiries_cmd.run,
    "compare": compare_cmd.run,
    "simulate": simulate_cmd.run,
    "backtest": backtest_cmd.run,
    "forward": forward_cmd.run,
    "keys": keys_cmd.run,
    "doctor": _doctor,
    "dashboard": _dashboard,
}


def main(argv=None):
    """Dispatch argv to the named subcommand and return its exit code."""
    args = build_parser().parse_args(argv)
    try:
        result = HANDLERS[args.command](args)
    except Exception as exc:
        # One error shape for every failure, so an agent parsing stdout does
        # not have to distinguish a traceback from a result.
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)},
                         indent=1))
        return 1
    print(json.dumps(result, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
