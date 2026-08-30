"""Model Context Protocol server over stdio, standard library only.

One server, every runtime. Claude Code, Codex and Gemini all speak MCP, so
the tools defined here are reachable from all three without writing a
separate adapter for each, and without adding a dependency that any of them
would have to install first.

The protocol surface implemented here is deliberately the minimum that a
client needs: initialize, the initialized notification, tools/list and
tools/call. Anything else gets a proper JSON-RPC method-not-found rather
than silence.

Transport detail that costs people hours: stdout carries protocol frames
only. Anything a tool wants to say to a human goes to stderr, because one
stray print corrupts the stream and the client reports a parse error with no
clue where it came from.
"""

import json
import sys

from optiondesk import __version__, engine_bridge
from optiondesk.artifacts import DISCLAIMER, artifact_dir
from optiondesk.cli import backtest as backtest_cmd
from optiondesk.cli import chain as chain_cmd
from optiondesk.cli import compare as compare_cmd
from optiondesk.cli import expiries as expiries_cmd
from optiondesk.cli import exposure as exposure_cmd
from optiondesk.cli import forward as forward_cmd
from optiondesk.cli import greeks as greeks_cmd
from optiondesk.cli import simulate as simulate_cmd
from optiondesk.cli import strategy as strategy_cmd
from optiondesk.providers import describe_all

PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "optiondesk"


class _Args:
    """argparse-free stand-in so CLI handlers can be called directly.

    Only parameters the tool advertises in its inputSchema are accepted
    from a caller. Everything else keeps its default. Copying arbitrary
    keys let a caller set out_dir, which is not advertised, and write a
    JSON file into any directory the process could create: write_json
    creates parents, so it was a directory-creating file write to an
    arbitrary path from an unauthenticated tool call.
    """

    def __init__(self, defaults, supplied, allowed):
        for key, value in defaults.items():
            setattr(self, key, value)
        self.rejected = []
        for key, value in (supplied or {}).items():
            if key in allowed:
                setattr(self, key, value)
            else:
                self.rejected.append(key)


TOOLS = [
    {
        "name": "option_chain_snapshot",
        "description": (
            "Retrieve an option chain for one underlying and expiry from a "
            "free data provider, solve implied volatility per contract where "
            "possible, and write a schema-validated snapshot artifact. "
            "Returns the artifact path and a summary. Delayed third-party "
            "data; not investment advice."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string",
                           "description": "Underlying ticker, e.g. SPY"},
                "expiry": {"type": "string",
                           "description": "YYYY-MM-DD. Omit for nearest"},
                "dividend_yield": {"type": "number",
                                   "description": "Continuous yield per 1.00"},
                "rate": {"type": "number",
                         "description": "Risk-free rate per 1.00. Omit to "
                                        "fetch the 13-week T-bill"},
            },
            "required": ["symbol"],
        },
        "handler": chain_cmd.run,
        "defaults": {"symbol": None, "expiry": None, "provider": None,
                     "rate": None, "dividend_yield": 0.0, "out_dir": None},
    },
    {
        "name": "option_greeks_ladder",
        "description": (
            "Compute the full first to third order Greek ladder (delta, "
            "gamma, vega, theta, rho, lambda, vanna, vomma, charm, veta, "
            "speed, zomma, color, ultima, dual delta, dual gamma) from a "
            "chain snapshot, using each contract's own implied volatility. "
            "Contracts without a usable volatility are skipped and counted, "
            "never defaulted. Requires the AGPL analytics engine."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "snapshot": {"type": "string",
                             "description": "Snapshot path. Omit for the "
                                            "most recent one"},
                "band": {"type": "number",
                         "description": "Keep strikes within this fraction "
                                        "of spot. 0 keeps all"},
                "type": {"type": "string",
                         "enum": ["call", "put", "both"]},
            },
        },
        "handler": greeks_cmd.run,
        "defaults": {"snapshot": None, "band": 0.10, "type": "both",
                     "out_dir": None},
    },
    {
        "name": "option_expiries",
        "description": (
            "List every expiry a provider carries for an underlying, with "
            "days to expiry, and mark which are already pulled. Omit the "
            "symbol to list only what is on disk, with no network access."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string",
                           "description": "Ticker. Omit for on-disk only"},
            },
        },
        "handler": expiries_cmd.run,
        "defaults": {"symbol": None, "provider": None, "out_dir": None},
    },
    {
        "name": "option_strategy_build",
        "description": (
            "Build one multi-leg structure from a chain snapshot: iron "
            "condor, iron butterfly, call butterfly, vertical spreads, "
            "straddle, strangle, covered call, cash-secured put, protective "
            "put, long call or put. Returns legs, breakevens, maximum gain "
            "and loss, model probability of profit, net Greeks and a "
            "friction estimate. Pass list to see the playbook, or an "
            "outlook from -2 to +2 to rank structures for a view."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string",
                         "description": "Strategy name, e.g. iron_condor"},
                "list_only": {"type": "boolean",
                              "description": "List the playbook instead"},
                "recommend": {"type": "string",
                              "description": "Outlook -2 to +2 to rank for"},
                "vol_view": {"type": "string",
                             "enum": ["neutral", "crush", "expand"]},
                "owns_underlying": {"type": "boolean"},
                "direction_unknown": {"type": "boolean"},
                "size": {"type": "number"},
                "snapshot": {"type": "string"},
            },
        },
        "handler": strategy_cmd.run,
        "defaults": {"name": None, "snapshot": None, "size": 1.0,
                     "underlying_entry": None, "out_dir": None,
                     "list_only": False, "recommend": None,
                     "vol_view": "neutral", "owns_underlying": False,
                     "direction_unknown": False},
    },
    {
        "name": "option_strategy_compare",
        "description": (
            "Build every structure from one chain and rank them by model "
            "expected profit per unit of capital at risk. Returns the full "
            "table, the leader, and the caveat that any positive "
            "expectation largely measures the gap between the model's "
            "single volatility and the market's smile. Not a "
            "recommendation."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "snapshot": {"type": "string"},
                "size": {"type": "number"},
                "include_underlying": {"type": "boolean"},
            },
        },
        "handler": compare_cmd.run,
        "defaults": {"snapshot": None, "size": 1.0,
                     "include_underlying": False, "rebuild": False,
                     "out_dir": None},
    },
    {
        "name": "option_positioning",
        "description": (
            "Dealer gamma exposure by strike, call and put walls, the gamma "
            "flip level, max pain, put-call ratios and volatility smile "
            "geometry (at-the-money volatility, 25-delta risk reversal, "
            "butterfly, skew slope, expected move). Signs assume dealers "
            "are long calls and short puts, which is stated in the output "
            "and is often wrong for a single name."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "snapshot": {"type": "string"},
                "multiplier": {"type": "number"},
            },
        },
        "handler": exposure_cmd.run,
        "defaults": {"snapshot": None, "multiplier": 100.0, "out_dir": None},
    },
    {
        "name": "option_simulate",
        "description": (
            "Fit a Bayesian GARCH(1,1)-t model to the underlying's realised "
            "returns by MCMC and simulate forward. Returns the posterior "
            "with convergence diagnostics, the predictive fan, value at "
            "risk and expected shortfall, and each saved structure's "
            "probability of profit under realised volatility next to the "
            "implied figure. Check converged before quoting any quantile."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "horizon": {"type": "integer",
                            "description": "Business days forward"},
                "paths": {"type": "integer"},
                "draws": {"type": "integer"},
                "period": {"type": "string",
                           "description": "History to fit, e.g. 2y"},
            },
            "required": ["symbol"],
        },
        "handler": simulate_cmd.run,
        "defaults": {"symbol": None, "horizon": 5, "paths": 20000,
                     "draws": 3000, "burn": 1000, "chains": 2,
                     "period": "2y", "provider": None,
                     "no_structures": False, "out_dir": None},
    },
    {
        "name": "option_backtest",
        "description": (
            "Run a structure across real price history with modelled "
            "premiums. Returns win rate, mean return on capital at risk, "
            "drawdown, a permutation test, a bootstrap interval and a "
            "buy-and-hold benchmark. Premiums are Black-Scholes values at "
            "trailing realised volatility, never fills; the honesty field "
            "states the limits and must be reported with any number."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "strategy": {"type": "string"},
                "holding_days": {"type": "integer"},
                "entry_every": {"type": "integer"},
                "period": {"type": "string"},
            },
            "required": ["symbol", "strategy"],
        },
        "handler": backtest_cmd.run,
        "defaults": {"symbol": None, "strategy": None, "holding_days": 30,
                     "entry_every": 5, "lookback": 60, "period": "5y",
                     "rate": 0.04, "dividend_yield": 0.0, "size": 1.0,
                     "provider": None, "out_dir": None},
    },
    {
        "name": "option_forward_test",
        "description": (
            "Paper ledger of positions recorded before their outcome is "
            "known. open records a structure from a plan, mark re-marks "
            "open positions against the newest chain, close settles one, "
            "status lists the ledger. Marks are mid quotes, not fills; a "
            "position with any leg missing from the newer chain comes back "
            "unmarkable rather than marked at zero."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string",
                           "enum": ["open", "mark", "close", "status"]},
                "strategy": {"type": "string"},
                "underlying": {"type": "string"},
                "position_id": {"type": "string"},
                "price": {"type": "number"},
                "thesis": {"type": "string"},
            },
            "required": ["action"],
        },
        "handler": forward_cmd.run,
        "defaults": {"action": "status", "plan": None, "strategy": None,
                     "underlying": None, "position_id": None, "price": None,
                     "thesis": None, "out_dir": None},
    },
    {
        "name": "option_desk_status",
        "description": (
            "Report which analytics engine and data providers are available, "
            "where artifacts are written, and which optional API keys are "
            "configured. Never returns a key value."),
        "inputSchema": {"type": "object", "properties": {}},
        "handler": lambda _args: {
            "shell_version": __version__,
            "artifact_dir": str(artifact_dir()),
            "engine": engine_bridge.status(),
            "providers": describe_all(),
            "disclaimer": DISCLAIMER,
        },
        "defaults": {},
    },
]

_BY_NAME = {tool["name"]: tool for tool in TOOLS}


def _public(tool):
    return {"name": tool["name"], "description": tool["description"],
            "inputSchema": tool["inputSchema"]}


def _result(payload):
    return {"content": [{"type": "text",
                         "text": json.dumps(payload, indent=1, default=str)}]}


def _error_result(exc):
    return {"content": [{"type": "text",
                         "text": json.dumps(
                             {"error": type(exc).__name__,
                              "message": str(exc)}, indent=1)}],
            "isError": True}


def handle(request):
    """Handle one JSON-RPC request. Returns a response dict, or None for a
    notification, which by protocol must not be answered."""
    if not isinstance(request, dict):
        # Well-formed JSON that is not an object, a batch array included,
        # previously reached request.get and killed the read loop, losing
        # every request queued behind it.
        return {"jsonrpc": "2.0", "id": None,
                "error": {"code": -32600,
                          "message": "invalid request: expected a JSON-RPC "
                                     "object, got {}".format(
                                         type(request).__name__)}}
    method = request.get("method")
    request_id = request.get("id")
    params = request.get("params") or {}

    if method == "initialize":
        # The specification requires the server to answer with a version it
        # supports. This server supports exactly one, so echoing the
        # client's string, which could be "not-a-version" or a dictionary,
        # is wrong even when it happens to match.
        return {
            "jsonrpc": "2.0", "id": request_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": __version__},
                "instructions": (
                    "Option analytics over free market data. Outputs are "
                    "research artifacts, not investment advice, and option "
                    "premiums are modelled values rather than tradable "
                    "quotes. Present the degraded flag whenever it is true."),
            },
        }

    if method in ("notifications/initialized", "initialized"):
        return None

    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id,
                "result": {"tools": [_public(t) for t in TOOLS]}}

    if method == "tools/call":
        name = params.get("name")
        tool = _BY_NAME.get(name)
        if tool is None:
            return {"jsonrpc": "2.0", "id": request_id,
                    "error": {"code": -32602,
                              "message": "unknown tool {!r}".format(name)}}
        allowed = set(tool["inputSchema"].get("properties") or {})
        args = _Args(tool["defaults"], params.get("arguments") or {}, allowed)
        try:
            payload = tool["handler"](args)
        except Exception as exc:  # surfaced to the model, not the transport
            return {"jsonrpc": "2.0", "id": request_id,
                    "result": _error_result(exc)}
        return {"jsonrpc": "2.0", "id": request_id, "result": _result(payload)}

    if request_id is None:
        return None
    return {"jsonrpc": "2.0", "id": request_id,
            "error": {"code": -32601,
                      "message": "method not found: {}".format(method)}}


def serve(stdin=None, stdout=None):
    """Read line-delimited JSON-RPC from stdin, write responses to stdout."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            stdout.write(json.dumps(
                {"jsonrpc": "2.0", "id": None,
                 "error": {"code": -32700,
                           "message": "parse error: {}".format(exc)}}) + "\n")
            stdout.flush()
            continue
        try:
            response = handle(request)
        except Exception as exc:
            # The transport outlives any single bad request. A handler that
            # raises returns an error frame; it does not end the session.
            response = {
                "jsonrpc": "2.0",
                "id": request.get("id") if isinstance(request, dict) else None,
                "error": {"code": -32603,
                          "message": "internal error: {}: {}".format(
                              type(exc).__name__, exc)}}
        if response is not None:
            stdout.write(json.dumps(response, default=str) + "\n")
            stdout.flush()


def main(argv=None):
    serve()
    return 0


if __name__ == "__main__":
    sys.exit(main())
