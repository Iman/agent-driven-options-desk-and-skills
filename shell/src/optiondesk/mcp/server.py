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

import base64
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
from optiondesk.cli import plots as plots_cmd
from optiondesk.cli import simulate as simulate_cmd
from optiondesk.cli import strategy as strategy_cmd
from optiondesk.providers import describe_all

PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "optiondesk"

USAGE = """usage: optiondesk-mcp [--help] [--version]

Model Context Protocol server for the option desk, spoken over stdio.
With no arguments it reads line-delimited JSON-RPC on standard input and
writes one response frame per request to standard output, until the client
closes the stream. It is meant to be launched by an MCP client, not typed
at a prompt.

Register it with a runtime:
  claude mcp add optiondesk -- /abs/path/to/.venv/bin/optiondesk-mcp
  codex  mcp add optiondesk -- /abs/path/to/.venv/bin/optiondesk-mcp
  gemini mcp add -s user optiondesk /abs/path/to/.venv/bin/optiondesk-mcp

Options:
  -h, --help     print this text and exit
  -V, --version  print the server version and exit
"""

# Appended to every tool description below. This server is the only surface
# Codex and Gemini get: neither loads the skill files that carry the desk's
# reporting discipline, so a rule that is not in the tool description does
# not reach those runtimes at all. Worded to stay true of the two tools
# whose summaries carry no degraded flag (option_desk_status, and
# option_forward_test, which reads no provider and is exempt by name in
# tests/test_summary_degraded_contract.py).
REPORTING_RULE = (
    " Before quoting any number from this result, state the degraded flag "
    "and its reason when the result carries one, and cite the artifact path "
    "it names.")


def _snapshot_schema(_args):
    """Describe the private user-data contract without reading data."""
    return chain_cmd.snapshot_schema()


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
        "name": "option_snapshot_schema",
        "description": (
            "Describe the accepted user-supplied CSV and JSON fields, column "
            "aliases, deterministic repair policy, size limits, and data-rights "
            "requirement. Call this when an attachment needs correction. Never "
            "invent a missing market value."),
        "inputSchema": {"type": "object", "properties": {}},
        "handler": _snapshot_schema,
        "defaults": {},
    },
    {
        "name": "option_chain_snapshot",
        "description": (
            "Retrieve an option chain for one underlying and expiry from a "
            "permitted provider or user-supplied data. An attachment can be "
            "sent as source_data, source_text, or a local source_path. Solve implied "
            "volatility where possible and write a schema-validated chain "
            "artifact for the dashboard and later tools. Set rights_confirmed "
            "only after the user states that the data can be sent for private "
            "analysis. Do not ask for an attachment again when it is present. "
            "Never invent a missing market value."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string",
                           "description": "Underlying ticker, e.g. SPY"},
                "expiry": {"type": "string",
                           "description": "YYYY-MM-DD. Omit for nearest"},
                "source_path": {"type": "string",
                                "description": "Path to a CSV or JSON snapshot"},
                "source_text": {"type": "string",
                                "description": "Inline CSV or JSON text"},
                "source_data": {
                    "description": "Inline JSON object or contract-row list",
                    "oneOf": [{"type": "object"}, {"type": "array"}]},
                "source_format": {"type": "string", "enum": ["csv", "json"]},
                "data_source": {
                    "type": "string",
                    "description": "Provider or source named by the user"},
                "rights_confirmed": {
                    "type": "boolean",
                    "description": "User states that this data can be sent "
                                   "for private analysis"},
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
                     "source_path": None, "from_file": None, "rate": None,
                     "source_text": None, "source_data": None,
                     "source_format": None, "data_source": None,
                     "rights_confirmed": False,
                     "dividend_yield": None, "out_dir": None},
    },
    {
        "name": "option_greeks_ladder",
        "description": (
            "Compute the full first to third order Greek ladder (delta, "
            "gamma, vega, theta, rho, lambda, vanna, vomma, charm, veta, "
            "speed, zomma, color, ultima, dual delta, dual gamma) from a "
            "chain snapshot, using each contract's own implied volatility. "
            "Contracts without a usable volatility are skipped and counted, "
            "never defaulted. Requires the analytics engine."),
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
        "name": "option_plots",
        "description": (
            "Fetch or read an option chain and return opaque PNG charts as "
            "image content in this tool result. Use this when the user asks "
            "to see, show, draw, chart, or plot option data. It displays the "
            "images in the conversation; do not start the localhost dashboard "
            "instead. The market image includes positioning when the analytics "
            "engine is available, plus open interest, volume, and implied "
            "volatility. A second image shows delta, gamma, theta, and vega."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string",
                           "description": "Underlying ticker, e.g. SPY"},
                "expiry": {"type": "string",
                           "description": "YYYY-MM-DD. Omit for nearest"},
                "snapshot": {"type": "string",
                             "description": "Existing chain artifact path"},
                "source_path": {"type": "string",
                                "description": "Uploaded CSV or JSON chain"},
                "source_text": {"type": "string",
                                "description": "Inline CSV or JSON text"},
                "source_data": {
                    "description": "Inline JSON object or contract-row list",
                    "oneOf": [{"type": "object"}, {"type": "array"}]},
                "source_format": {"type": "string", "enum": ["csv", "json"]},
                "data_source": {"type": "string"},
                "rights_confirmed": {"type": "boolean"},
                "rate": {"type": "number"},
                "dividend_yield": {"type": "number"},
                "band": {"type": "number",
                         "description": "Fraction around spot; 0 shows all"},
            },
            "required": ["symbol"],
        },
        "handler": plots_cmd.run,
        "defaults": {"symbol": None, "expiry": None, "snapshot": None,
                     "source_path": None, "rate": None,
                     "source_text": None, "source_data": None,
                     "source_format": None, "data_source": None,
                     "rights_confirmed": False,
                     "dividend_yield": None, "band": 0.15,
                     "out_dir": None},
        "returns_images": True,
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
                # Advertised as an integer, not a string, because the handler
                # spends it as one: cli/strategy.py calls int() on it before
                # anything else touches it, and the domain is the five
                # outlooks -2 to +2. A schema-validating client rejected the
                # integer a model naturally sends for "outlook -2 to +2",
                # and the string a client sent instead only worked because
                # int() happens to parse "1". The type now says what the
                # value is rather than how it survives the trip.
                "recommend": {"type": "integer",
                              "description": "Outlook -2 to +2 to rank for"},
                "vol_view": {"type": "string",
                             "enum": ["neutral", "crush", "expand"]},
                "owns_underlying": {"type": "boolean"},
                "direction_unknown": {"type": "boolean"},
                "size": {"type": "number"},
                "snapshot": {"type": "string"},
                # The two-expiry structures this tool advertises as buildable
                # need these three. Semantics are the CLI's, from
                # cli/strategy.py add_arguments: the later chain, which side
                # a time spread is built from, and how far out of the money a
                # diagonal sells its near leg.
                "far_snapshot": {
                    "type": "string",
                    "description": "The later expiry, for a calendar or "
                                   "diagonal. Omit and the nearest later "
                                   "chain on disk for the same underlying "
                                   "is used"},
                "kind": {"type": "string", "enum": ["call", "put"],
                         "description": "Which side a time spread is built "
                                        "from"},
                "offset": {"type": "number",
                           "description": "How far out of the money a "
                                          "diagonal sells the near leg, as "
                                          "a fraction of spot"},
            },
        },
        "handler": strategy_cmd.run,
        "defaults": {"name": None, "snapshot": None, "size": 1.0,
                     "underlying_entry": None, "out_dir": None,
                     "list_only": False, "recommend": None,
                     "vol_view": "neutral", "owns_underlying": False,
                     "direction_unknown": False,
                     # Same defaults argparse gives them, so a call that
                     # omits them behaves exactly as the CLI does.
                     "far_snapshot": None, "kind": "call", "offset": 0.03},
    },
    {
        "name": "option_strategy_compare",
        "description": (
            "Build every structure in the playbook from one chain, "
            "including the calendar and the diagonal when a later expiry "
            "is on disk, and rank them by model expected profit per unit "
            "of capital at risk. Returns the full "
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
                "far_snapshot": {"type": "string"},
            },
        },
        "handler": compare_cmd.run,
        "defaults": {"snapshot": None, "size": 1.0,
                     "include_underlying": False, "rebuild": False,
                     "far_snapshot": None, "out_dir": None},
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


# Applied in a loop rather than typed into each description, so a tool added
# later cannot ship without the rule. Nine of the ten descriptions carried no
# reporting instruction at all, and DISCLAIMER reached exactly one result.
for _tool in TOOLS:
    _tool["description"] += REPORTING_RULE
del _tool


def _hints(read_only, destructive, idempotent, open_world):
    """The four MCP tool annotations, every one stated.

    A client treats a missing hint as its default (readOnly false,
    destructive true, idempotent false, openWorld true), so leaving one out
    is a claim too, and for most of these tools the wrong one.
    """
    return {"readOnlyHint": read_only, "destructiveHint": destructive,
            "idempotentHint": idempotent, "openWorldHint": open_world}


# What each kind of tool does to the machine it runs on, read from the
# runners rather than from their descriptions.
#
# Writers are not destructive: write_json moves the artifact it replaces
# into archive/<date>/ under a timestamp, so nothing is lost (unless the
# operator has set OPTIONDESK_ARCHIVE=0). They are not idempotent either:
# every run stamps a new generated_utc, so a repeat writes a new artifact
# and archives the previous one rather than leaving the directory as it
# was.
#
# openWorld is whether the runner can reach a data provider. It is true for
# a tool that fetches when no local input is given, even though the same
# tool reads a user file without touching the network.
_FETCHES_AND_WRITES = _hints(False, False, False, True)
_WRITES_FROM_DISK = _hints(False, False, False, False)
_READS_ONLY = _hints(True, False, True, False)

# name: (title, annotations). Every tool must appear here: the loop below
# raises at import for one that does not, so a tool cannot ship without
# its hints.
_METADATA = {
    "option_snapshot_schema": ("Snapshot schema", _READS_ONLY),
    # chain, plots, simulate and backtest resolve a provider unless given
    # a snapshot or a user file, and all four write artifacts. plots also
    # writes the PNGs it returns, and runs greeks and exposure when their
    # artifacts are missing or older than the chain.
    "option_chain_snapshot": ("Chain snapshot", _FETCHES_AND_WRITES),
    "option_plots": ("Option plots", _FETCHES_AND_WRITES),
    "option_simulate": ("Simulation", _FETCHES_AND_WRITES),
    "option_backtest": ("Backtest", _FETCHES_AND_WRITES),
    # expiries asks the provider for its list when a symbol is given and
    # writes nothing either way: it reads the artifact directory to mark
    # what is already pulled and returns rows.
    "option_expiries": ("Expiries", _FETCHES_AND_WRITES),
    # These four read a chain snapshot from the artifact directory and
    # write a ladder, a plan, a comparison or an exposure beside it.
    "option_greeks_ladder": ("Greek ladder", _WRITES_FROM_DISK),
    "option_strategy_build": ("Strategy build", _WRITES_FROM_DISK),
    "option_strategy_compare": ("Strategy compare", _WRITES_FROM_DISK),
    "option_positioning": ("Positioning", _WRITES_FROM_DISK),
    # One tool, four verbs, one set of hints for the whole. status only
    # reads, but open appends a position, mark appends marks, and close
    # settles an open position with no verb to reopen it, so the tool as a
    # whole is a non-idempotent, destructive writer. Marks come from chain
    # snapshots already on disk, so no provider is reached.
    "option_forward_test": ("Forward test",
                            _hints(False, True, False, False)),
    # Reads the engine's import status and each provider's availability,
    # which is an import and a key check rather than a request.
    "option_desk_status": ("Desk status", _READS_ONLY),
}

# Output schemas only where the runner's return dict has one shape. The
# other tools return dicts whose keys depend on the branch taken (a plan
# build against list_only, four forward verbs, a fetched chain against a
# user file), and a schema saying "object" and nothing more would be a
# promise without content. A declared schema obliges the server to return
# structuredContent conforming to it, which _result does for these two.
_STRINGS = {"type": "array", "items": {"type": "string"}}
_STATUS_OUTPUT = {
    "type": "object",
    "properties": {
        "shell_version": {"type": "string"},
        "artifact_dir": {"type": "string"},
        "engine": {
            "type": "object",
            "properties": {
                "available": {"type": "boolean"},
                "package": {"type": "string"},
                "version": {"type": ["string", "null"]},
                "license": {"type": ["string", "null"]},
                "message": {"type": ["string", "null"]},
            },
            "required": ["available", "package", "version", "license",
                         "message"],
        },
        "providers": {"type": "object"},
        "disclaimer": {"type": "string"},
        "ignored_arguments": _STRINGS,
    },
    "required": ["shell_version", "artifact_dir", "engine", "providers",
                 "disclaimer"],
}
_SNAPSHOT_SCHEMA_OUTPUT = {
    "type": "object",
    "properties": {
        "purpose": {"type": "string"},
        "accepted_inputs": _STRINGS,
        "required_metadata": _STRINGS,
        "recommended_metadata": _STRINGS,
        "required_contract_fields": _STRINGS,
        "recommended_contract_fields": _STRINGS,
        "aliases": {"type": "object"},
        "repair_policy": {"type": "string"},
        "rights": {"type": "string"},
        "limits": {
            "type": "object",
            "properties": {"bytes": {"type": "integer"},
                           "rows": {"type": "integer"}},
            "required": ["bytes", "rows"],
        },
        "disclaimer": {"type": "string"},
        "ignored_arguments": _STRINGS,
    },
    "required": ["purpose", "accepted_inputs", "required_metadata",
                 "recommended_metadata", "required_contract_fields",
                 "recommended_contract_fields", "aliases", "repair_policy",
                 "rights", "limits", "disclaimer"],
}
_OUTPUT_SCHEMAS = {
    "option_desk_status": _STATUS_OUTPUT,
    "option_snapshot_schema": _SNAPSHOT_SCHEMA_OUTPUT,
}

for _tool in TOOLS:
    _tool["title"], _tool["annotations"] = _METADATA[_tool["name"]]
    if _tool["name"] in _OUTPUT_SCHEMAS:
        _tool["outputSchema"] = _OUTPUT_SCHEMAS[_tool["name"]]
del _tool

_BY_NAME = {tool["name"]: tool for tool in TOOLS}


def _public(tool):
    """The wire form of one tool: what tools/list shows and nothing internal.

    The title and the four hints travel with every tool, the output schema
    with the two whose result has one shape. The handler, the defaults and
    the image flag stay here. Before this, tools/list carried name,
    description and inputSchema alone, so a client saw every tool as an
    unhinted writer that might reach the network.
    """
    public = {"name": tool["name"], "title": tool["title"],
              "description": tool["description"],
              "inputSchema": tool["inputSchema"],
              # Inside annotations as well: clients written to the earlier
              # revision of the protocol look for the title there.
              "annotations": dict(tool["annotations"], title=tool["title"])}
    if tool.get("outputSchema"):
        public["outputSchema"] = tool["outputSchema"]
    return public


def _result(payload, rejected=(), image_paths=(), structured=False):
    """One tools/call result frame.

    Two things travel with every payload rather than with one of them.

    The disclaimer, because a result is where a number is read. It was
    carried by option_desk_status alone, which is the one tool that reports
    no numbers, so the tools a model actually quotes from carried nothing.
    setdefault, so a handler that already supplies its own keeps it.

    The arguments that were dropped, under the same key the LangChain
    bindings use (agent/src/optiondesk_agent/tools.py). Silence let a caller
    believe an unadvertised argument had been honoured: a model passing
    out_dir got a normal-looking result written somewhere else entirely.

    structured is true for a tool that advertises an outputSchema: the
    protocol then requires the same object as structuredContent, beside the
    text every client can read.
    """
    if isinstance(payload, dict):
        payload = dict(payload)
        payload.setdefault("disclaimer", DISCLAIMER)
        if rejected:
            payload["ignored_arguments"] = list(rejected)
    content = [{"type": "text",
                "text": json.dumps(payload, indent=1, default=str)}]
    for path in image_paths:
        with open(path, "rb") as handle:
            content.append({
                "type": "image",
                "data": base64.b64encode(handle.read()).decode("ascii"),
                "mimeType": "image/png",
            })
    result = {"content": content}
    if structured and isinstance(payload, dict):
        result["structuredContent"] = payload
    return result


def _error_result(exc):
    """A failure, as an isError result the model reads rather than a
    transport error.

    It carries the disclaimer a success carries. A refusal names the
    provider, the file or the terms that stopped the run, and a model
    quotes that text as readily as a number; for Codex and Gemini this
    frame is the only place the boundary can be stated.
    """
    return {"content": [{"type": "text",
                         "text": json.dumps(
                             {"error": type(exc).__name__,
                              "message": str(exc),
                              "disclaimer": DISCLAIMER}, indent=1)}],
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

    # A notification carries no id, and by protocol gets no response. This
    # check has to come before the dispatch below, not after it. Sitting
    # after, it suppressed only the frame: a tools/call sent as a
    # notification still ran, wrote an artifact, and was then answered with
    # an unsolicited "id": null response the client had nothing to match.
    # The test is the absence of the member, not a null id, because 0 is a
    # legal JSON-RPC id and a request carrying it must still be answered.
    if "id" not in request:
        return None

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
                    "Option analytics over permitted or user-supplied data. "
                    "When a file is attached, use it instead of asking for it "
                    "again. Correct clear format and unit errors, report each "
                    "repair, and never invent a missing market value. User data "
                    "is for private analysis only. Outputs are research "
                    "artifacts, not investment advice. Present the degraded "
                    "flag whenever it is true."),
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
        supplied = params.get("arguments") or {}
        if not isinstance(supplied, dict):
            # A client sending a string or a list here used to reach
            # .get() and come back as -32603 internal error, which tells a
            # model the server broke rather than that the call was malformed
            # and blames the wrong side of the connection.
            return {"jsonrpc": "2.0", "id": request_id,
                    "error": {"code": -32602,
                              "message": "arguments must be an object, got "
                                         "{}".format(
                                             type(supplied).__name__)}}
        # inputSchema.required was published and never enforced, so a
        # required argument left out reached the handler as its None default
        # and failed somewhere inside it: an empty arguments object on
        # option_chain_snapshot came back as "'NoneType' object has no
        # attribute 'upper'", which names neither the tool nor the argument
        # and gives a model nothing to correct. An explicit null is the same
        # omission and is treated the same way.
        missing = [key for key in (tool["inputSchema"].get("required") or [])
                   if supplied.get(key) is None]
        if missing:
            return {"jsonrpc": "2.0", "id": request_id,
                    "error": {"code": -32602,
                              "message": "{} is missing required {}: {}"
                                         .format(
                                             name,
                                             "argument" if len(missing) == 1
                                             else "arguments",
                                             ", ".join(missing))}}
        allowed = set(tool["inputSchema"].get("properties") or {})
        args = _Args(tool["defaults"], supplied, allowed)
        try:
            payload = tool["handler"](args)
            image_paths = (payload.get("plots") or []) if (
                tool.get("returns_images") and isinstance(payload, dict)) else []
            result = _result(payload, args.rejected, image_paths,
                             structured=bool(tool.get("outputSchema")))
        except Exception as exc:  # surfaced to the model, not the transport
            return {"jsonrpc": "2.0", "id": request_id,
                    "result": _error_result(exc)}
        return {"jsonrpc": "2.0", "id": request_id,
                "result": result}

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
    """Serve the JSON-RPC loop on stdin and stdout until the client closes it.

    argv is read rather than ignored. Ignored, every argument fell through to
    serve(), so 'optiondesk-mcp --help' printed nothing and blocked on stdin
    with no prompt back and no hint that it was waiting. Help and version
    answer and exit without reading stdin at all; an unrecognised argument
    says so on stderr rather than silently becoming a server.

    Help goes to stdout because that is where a person asking for it looks.
    The stdout-is-protocol-only rule holds for the serving path below, which
    these branches return before reaching.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    if "-h" in argv or "--help" in argv:
        sys.stdout.write(USAGE)
        return 0
    if "-V" in argv or "--version" in argv:
        sys.stdout.write("{} {}\n".format(SERVER_NAME, __version__))
        return 0
    if argv:
        sys.stderr.write("optiondesk-mcp: unrecognised argument: {}\n\n{}"
                         .format(" ".join(argv), USAGE))
        return 2
    serve()
    return 0


if __name__ == "__main__":
    sys.exit(main())
