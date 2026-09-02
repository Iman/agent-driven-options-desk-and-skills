"""MCP surface. These are the calls every runtime makes before anything
else, so a regression here breaks Claude Code, Codex and Gemini at once."""

import argparse
import base64
import io
import json

import pytest

from optiondesk.artifacts import DISCLAIMER, write_json
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
from optiondesk.mcp import server

from marks import needs_engine


def test_initialize_reports_tools_capability():
    response = server.handle({"jsonrpc": "2.0", "id": 1,
                              "method": "initialize",
                              "params": {"protocolVersion": "2025-06-18"}})
    assert response["id"] == 1
    result = response["result"]
    assert result["protocolVersion"] == "2025-06-18"
    assert "tools" in result["capabilities"]
    assert result["serverInfo"]["name"] == "optiondesk"
    assert "not investment advice" in result["instructions"]


def test_initialized_notification_is_not_answered():
    assert server.handle({"jsonrpc": "2.0",
                          "method": "notifications/initialized"}) is None


def test_tools_list_shape():
    response = server.handle({"jsonrpc": "2.0", "id": 2,
                              "method": "tools/list"})
    tools = response["result"]["tools"]
    names = {tool["name"] for tool in tools}
    # Every capability the desk has must be reachable over MCP, since that
    # is the only path an agent runtime has to it.
    assert {"option_chain_snapshot", "option_greeks_ladder",
            "option_expiries", "option_strategy_build",
            "option_strategy_compare", "option_positioning",
            "option_plots", "option_snapshot_schema",
            "option_simulate", "option_backtest", "option_forward_test",
            "option_desk_status"} <= names
    assert len(names) == len(tools), "duplicate tool name"
    for tool in tools:
        assert tool["description"]
        assert tool["inputSchema"]["type"] == "object"
        # No internal keys may leak into the wire format.
        assert set(tool) == {"name", "description", "inputSchema"}


def test_status_tool_call_returns_json_content():
    response = server.handle({
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "option_desk_status", "arguments": {}}})
    content = response["result"]["content"][0]
    assert content["type"] == "text"
    payload = json.loads(content["text"])
    assert "engine" in payload and "providers" in payload
    assert "disclaimer" in payload


def test_snapshot_schema_tells_chat_what_it_can_repair():
    payload = body_of(call("option_snapshot_schema"))
    assert "source_data" in " ".join(payload["accepted_inputs"])
    assert payload["limits"]["rows"] == chain_cmd.MAX_USER_ROWS
    assert "Never invent" in payload["repair_policy"]


def test_inline_user_snapshot_reaches_the_local_artifact_desk(desk):
    response = call("option_chain_snapshot", {
        "symbol": "SPY",
        "source_data": {
            "underlying": "SPY",
            "spot": 600,
            "snapshot_timestamp": "2026-09-02T14:00:00Z",
            "expiry": "2026-09-18",
            "contracts": [
                {"strike": 600, "type": "call", "bid": 5.2,
                 "ask": 5.6, "iv": 0.22},
                {"strike": 600, "type": "put", "bid": 4.8,
                 "ask": 5.0, "iv": 0.24},
            ],
        },
        "data_source": "user broker export",
        "rights_confirmed": True,
        "rate": 0.05,
        "dividend_yield": 0.0,
    })
    assert not response["result"].get("isError"), response
    payload = body_of(response)
    assert payload["data_source"] == "user broker export"
    assert payload["normalization"]["output_contracts"] == 2
    assert (desk / "chain_SPY_2026-09-18.json").is_file()


def test_unknown_tool_is_a_protocol_error():
    response = server.handle({
        "jsonrpc": "2.0", "id": 4, "method": "tools/call",
        "params": {"name": "nope", "arguments": {}}})
    assert response["error"]["code"] == -32602


def test_tool_failure_is_reported_to_the_model_not_the_transport():
    # A tool that raises must come back as an isError result, because a
    # JSON-RPC error would make the client treat the server as broken.
    response = server.handle({
        "jsonrpc": "2.0", "id": 5, "method": "tools/call",
        "params": {"name": "option_greeks_ladder",
                   "arguments": {"snapshot": "/nonexistent/path.json"}}})
    assert "error" not in response
    assert response["result"]["isError"] is True


def test_unknown_method_returns_method_not_found():
    response = server.handle({"jsonrpc": "2.0", "id": 6,
                              "method": "resources/list"})
    assert response["error"]["code"] == -32601


def test_serve_loop_writes_one_line_per_request():
    stdin = io.StringIO(
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {}}) + "\n"
        + json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
        + "\n"
        + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        + "\n")
    stdout = io.StringIO()
    server.serve(stdin, stdout)
    lines = [line for line in stdout.getvalue().splitlines() if line.strip()]
    # Two requests, one notification, so exactly two responses.
    assert len(lines) == 2
    assert json.loads(lines[0])["id"] == 1
    assert json.loads(lines[1])["id"] == 2


# ------------------------------------------------- hardening regressions

def test_a_non_object_request_does_not_kill_the_session():
    """One stray line used to end the server and lose everything queued."""
    lines = [
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
        json.dumps([1, 2, 3]),          # a JSON-RPC batch, removed in 2025-06-18
        json.dumps("a bare string"),
        json.dumps(42),
        json.dumps(None),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "ping"}),
    ]
    out = io.StringIO()
    server.serve(io.StringIO("\n".join(lines) + "\n"), out)
    responses = [json.loads(line) for line in out.getvalue().splitlines()
                 if line.strip()]
    assert len(responses) == 6
    assert responses[0]["id"] == 1
    for bad in responses[1:5]:
        assert bad["error"]["code"] == -32600
    # The request queued behind the bad lines still gets answered.
    assert responses[5]["id"] == 2


def test_protocol_version_is_the_one_this_server_supports():
    # The specification requires a version the server supports, not an echo.
    for requested in ("1999-01-01", "not-a-version", "", {"evil": 1}):
        response = server.handle({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": requested}})
        assert response["result"]["protocolVersion"] == server.PROTOCOL_VERSION


def test_unadvertised_arguments_are_refused(tmp_path):
    """out_dir is a handler default, not an advertised parameter.

    Accepting it from a caller turned a tool call into a file write to any
    path the process could create, since the artifact writer creates parent
    directories.
    """
    target = tmp_path / "should_not_exist"
    response = server.handle({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "option_desk_status",
                   "arguments": {"out_dir": str(target),
                                 "provider": "made_up"}}})
    assert "error" not in response
    assert not target.exists()


def test_handler_exceptions_do_not_escape_the_transport():
    class Boom:
        def get(self, *args, **kwargs):
            raise RuntimeError("exploding request object")

    out = io.StringIO()
    # A request object that misbehaves must still produce a frame.
    response = server.handle({"jsonrpc": "2.0", "id": 1,
                              "method": "tools/call",
                              "params": {"name": "option_greeks_ladder",
                                         "arguments": {"band": "not a number"}}})
    assert response["result"]["isError"] is True
    assert out.getvalue() == ""


# ------------------------------------------- defects reproduced over stdio
#
# Every test above this line drives option_desk_status, the one tool that
# reads nothing, writes nothing and calls no CLI handler. That is why the
# first two defects below shipped green: a suite that never calls a real
# tool cannot watch a real tool crash, and a suite whose only notification
# is the one method the dispatcher special-cases cannot watch a
# notification be executed and answered.

# The CLI module behind each tool. The parser in that module is the list of
# attributes its run() may read, which is the contract the tool defaults
# have to satisfy.
CLI_BEHIND = {
    "option_chain_snapshot": chain_cmd,
    "option_greeks_ladder": greeks_cmd,
    "option_plots": plots_cmd,
    "option_expiries": expiries_cmd,
    "option_strategy_build": strategy_cmd,
    "option_strategy_compare": compare_cmd,
    "option_positioning": exposure_cmd,
    "option_simulate": simulate_cmd,
    "option_backtest": backtest_cmd,
    "option_forward_test": forward_cmd,
}

# Tool calls that complete without a network provider: they read the
# artifact directory or nothing at all. A test that needs a provider to
# answer is a test that does not run.
OFFLINE_CALLS = [
    ("option_desk_status", {}),
    ("option_strategy_build", {"list_only": True}),
    ("option_expiries", {}),
    ("option_greeks_ladder", {}),
    ("option_positioning", {}),
    ("option_strategy_compare", {}),
    ("option_forward_test", {"action": "status"}),
]


@pytest.fixture
def desk(tmp_path, monkeypatch):
    """Point every artifact read and write at a temporary directory.

    out_dir is deliberately not an advertised parameter, so a test cannot
    pass one through a tool call. The environment variable is the supported
    way to move the directory, and without it these tests would write into
    the operator's real ~/TradingDesk/option-desk.
    """
    monkeypatch.setenv("OPTIONDESK_ARTIFACTS", str(tmp_path))
    return tmp_path


def call(name, arguments=None, request_id=1):
    """One tools/call request, as a client sends it."""
    return server.handle({"jsonrpc": "2.0", "id": request_id,
                          "method": "tools/call",
                          "params": {"name": name,
                                     "arguments": arguments or {}}})


def test_plot_tool_returns_opaque_png_content(
        desk, chain_snapshot, monkeypatch):
    """A plot request must put an image in the MCP result itself."""
    snapshot = chain_snapshot(expiry="2026-09-18", days=16.0)
    path = write_json(snapshot, "chain_TEST_2026-09-18.json", desk)
    monkeypatch.setattr(plots_cmd.engine_bridge, "AVAILABLE", False)

    response = call("option_plots", {
        "symbol": "TEST", "snapshot": str(path)})
    assert not response["result"].get("isError"), response
    blocks = response["result"]["content"]
    assert blocks[0]["type"] == "text"
    images = [block for block in blocks if block["type"] == "image"]
    assert len(images) == 1
    assert images[0]["mimeType"] == "image/png"
    decoded = base64.b64decode(images[0]["data"])
    assert decoded.startswith(b"\x89PNG\r\n\x1a\n")
    assert decoded[25] == 2, "PNG must use opaque RGB, not RGBA"


def body_of(response):
    """The JSON a tool result carries, which is what the model reads."""
    return json.loads(response["result"]["content"][0]["text"])


def two_expiry_chains(chain_snapshot, directory):
    """A near and a far chain for the same underlying, on disk."""
    near = chain_snapshot(expiry="2026-09-18", days=30.0)
    far = chain_snapshot(expiry="2026-10-16", days=58.0)
    write_json(near, "chain_TEST_2026-09-18.json", directory)
    write_json(far, "chain_TEST_2026-10-16.json", directory)
    return near, far


# --------------------------------------------------- 1. two-expiry structures

def test_the_two_expiry_parameters_are_advertised():
    """WHAT WOULD BREAK. option_strategy_build tells a model that calendar
    and diagonal spreads are buildable and published no way to say which
    later expiry to use, which side to build from, or how far a diagonal
    leans. A model could only call it with the near chain and hope.
    """
    tools = server.handle({"jsonrpc": "2.0", "id": 1,
                           "method": "tools/list"})["result"]["tools"]
    build = next(t for t in tools if t["name"] == "option_strategy_build")
    properties = build["inputSchema"]["properties"]
    assert {"far_snapshot", "kind", "offset"} <= set(properties)
    assert properties["kind"]["enum"] == ["call", "put"]
    assert properties["far_snapshot"]["type"] == "string"
    assert properties["offset"]["type"] == "number"


def test_the_tool_defaults_cover_every_argument_its_handler_can_read():
    """WHAT WOULD BREAK. The handler is a CLI run() and reads whatever its
    own parser defines. A parser destination with no entry in the tool
    defaults is an AttributeError waiting for the first caller who takes
    the branch that reads it, and that is exactly how a calendar spread
    came to crash with "'_Args' object has no attribute 'far_snapshot'".
    """
    for tool in server.TOOLS:
        module = CLI_BEHIND.get(tool["name"])
        if module is None:
            continue
        parser = module.add_arguments(argparse.ArgumentParser())
        destinations = {action.dest for action in parser._actions
                        if action.dest != "help"}
        missing = sorted(destinations - set(tool["defaults"]))
        assert not missing, (
            "{} calls {}.run, which may read {}, and the tool sets no "
            "default for them".format(tool["name"], module.__name__,
                                      missing))


@needs_engine
def test_every_two_expiry_structure_the_tool_advertises_can_be_built(
        desk, chain_snapshot):
    """WHAT WOULD BREAK. The same tool call that reports calendar_spread
    and diagonal_spread as buildable crashed on both of them. Reproduced
    over stdio as "'_Args' object has no attribute 'far_snapshot'" from a
    structure the tool had just named as available, while both build
    through the CLI.

    Driven from list_only rather than a hardcoded pair, so a structure
    added to the playbook later is covered the day it is advertised.
    """
    two_expiry_chains(chain_snapshot, desk)

    listed = body_of(call("option_strategy_build", {"list_only": True}))
    advertised = [entry["name"] for entry in listed["strategies"]
                  if entry["needs_two_expiries"] and entry["buildable"]]
    assert advertised, "the playbook no longer advertises a time spread"

    for name in advertised:
        response = call("option_strategy_build", {"name": name})
        assert "error" not in response, (name, response)
        body = body_of(response)
        assert not response["result"].get("isError"), (name, body)
        assert body["built"] is True, (name, body)
        assert body["far_days"] > body["near_days"], (name, body)


@needs_engine
def test_the_advertised_time_spread_parameters_reach_the_handler(
        desk, chain_snapshot):
    """Advertising them is only half of it: they have to arrive.

    far_snapshot names the far chain explicitly and kind picks the side, so
    a build that honours them differs from the default build in a way the
    result shows.
    """
    two_expiry_chains(chain_snapshot, desk)
    far_path = str(desk / "chain_TEST_2026-10-16.json")

    body = body_of(call("option_strategy_build",
                        {"name": "calendar_spread",
                         "far_snapshot": far_path, "kind": "put"}))
    assert body["built"] is True
    assert all(leg["kind"] == "put" for leg in body["legs"]), body["legs"]
    assert body["far_expiry"] == "2026-10-16"

    # The default side is the call side, so the two builds differ. Without
    # that, "kind arrived" and "kind was ignored" look the same.
    default = body_of(call("option_strategy_build",
                           {"name": "calendar_spread"}))
    assert all(leg["kind"] == "call" for leg in default["legs"])


# ------------------------------------------------------- 2. notifications

def test_a_tools_call_notification_is_not_answered():
    """WHAT WOULD BREAK. The notification guard sat after the dispatch, so
    a notification was executed and then answered with an unsolicited
    "id": null frame the client had no request to match it to.

    The one notification the old suite sent was notifications/initialized,
    which the dispatcher returns None for by name, so the guard below it
    was never the thing under test.
    """
    assert server.handle({"jsonrpc": "2.0", "method": "tools/call",
                          "params": {"name": "option_desk_status",
                                     "arguments": {}}}) is None


@needs_engine
def test_a_tools_call_notification_does_not_run_the_tool(desk,
                                                         chain_snapshot):
    """The frame was the visible half. The tool ran.

    A notification cannot be answered, so a tool driven by one can report
    neither success nor failure to anybody, and this one wrote an artifact
    on its way to being unreportable.
    """
    two_expiry_chains(chain_snapshot, desk)
    assert server.handle({
        "jsonrpc": "2.0", "method": "tools/call",
        "params": {"name": "option_strategy_build",
                   "arguments": {"name": "calendar_spread"}}}) is None
    assert not list(desk.glob("strategy_*.json")), (
        "a notification wrote an artifact")


def test_serve_does_not_emit_a_frame_for_a_notification():
    """The same defect at the transport, where the client sees it."""
    lines = [
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
        json.dumps({"jsonrpc": "2.0", "method": "tools/call",
                    "params": {"name": "option_desk_status",
                               "arguments": {}}}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "ping"}),
    ]
    out = io.StringIO()
    server.serve(io.StringIO("\n".join(lines) + "\n"), out)
    frames = [json.loads(line) for line in out.getvalue().splitlines()
              if line.strip()]
    assert [frame["id"] for frame in frames] == [1, 2]


def test_a_request_carrying_id_zero_is_still_answered():
    """The guard has to test for the absence of the id member, not for a
    falsy one. 0 is a legal JSON-RPC id, and a guard written as
    "request_id is None" moved above the dispatch would drop the request
    silently, turning one defect into another.

    This passes against the unfixed server too: it is here to stop the
    obvious fix from introducing the bug it does not have yet.
    """
    response = server.handle({"jsonrpc": "2.0", "id": 0,
                              "method": "tools/list"})
    assert response is not None
    assert response["id"] == 0


# ------------------------------------------------- 3. required arguments

def test_a_missing_required_argument_is_named_in_a_protocol_error(
        desk, stub_provider):
    """WHAT WOULD BREAK. inputSchema.required was published and never
    enforced. option_chain_snapshot with an empty arguments object reached
    the handler with symbol still None and came back as "'NoneType' object
    has no attribute 'upper'", which names neither the tool nor the
    argument and gives a model nothing to correct.

    A stub provider is registered so that the unfixed path this test exists
    to catch runs offline instead of reaching for the network.
    """
    stub_provider()
    response = call("option_chain_snapshot", {})
    assert response["error"]["code"] == -32602
    assert "symbol" in response["error"]["message"]
    assert "option_chain_snapshot" in response["error"]["message"]


def test_no_handler_runs_when_a_required_argument_is_missing(
        desk, monkeypatch):
    """Enforcement has to hold for every tool that declares required, not
    just the one that was reported. The handler is replaced by a recorder,
    so this stays offline and proves the stronger property: the tool is
    never entered at all.
    """
    entered = []
    for tool in server.TOOLS:
        required = tool["inputSchema"].get("required") or []
        if not required:
            continue
        monkeypatch.setitem(
            tool, "handler",
            lambda _args, _name=tool["name"]: entered.append(_name))
        response = call(tool["name"], {})
        assert "error" in response, (tool["name"], response)
        assert response["error"]["code"] == -32602
        for key in required:
            assert key in response["error"]["message"], (tool["name"], key)
    assert entered == [], (
        "these handlers ran with a required argument missing: {}".format(
            entered))


def test_an_explicit_null_is_the_same_omission(desk, stub_provider):
    """Sending the key with a null value leaves the handler holding the
    same None it would have had from the default, so it is refused the
    same way rather than reaching the handler through a gap in the check.
    """
    stub_provider()
    response = call("option_chain_snapshot", {"symbol": None})
    assert response["error"]["code"] == -32602
    assert "symbol" in response["error"]["message"]


# --------------------------------------------- 4. arguments that were dropped

def test_dropped_arguments_are_named_in_the_result(desk):
    """WHAT WOULD BREAK. _Args recorded every unadvertised key in
    args.rejected and nothing ever read it. A caller passing out_dir got a
    result that looked entirely normal and an artifact written somewhere
    else, with no signal that the argument had been ignored.

    The key is the one the LangChain bindings already use, so the two
    surfaces report the same thing by the same name.
    """
    body = body_of(call("option_desk_status",
                        {"out_dir": "/tmp/should-not-be-used",
                         "provider": "made_up"}))
    assert body["ignored_arguments"] == ["out_dir", "provider"]


def test_a_result_with_nothing_dropped_carries_no_such_key(desk):
    """An empty list on every result would train a reader to skip it."""
    assert "ignored_arguments" not in body_of(call("option_desk_status", {}))


# ------------------------------------------------------ 5. the command line

class _ExplodingStdin:
    """Standard input that fails loudly rather than blocking a test."""

    def __iter__(self):
        raise AssertionError("stdin was read")

    def readline(self):
        raise AssertionError("stdin was read")


def test_help_prints_and_exits_without_reading_stdin(monkeypatch, capsys):
    """WHAT WOULD BREAK. main took argv and ignored it, so every argument
    fell through into the serving loop. 'optiondesk-mcp --help' printed
    nothing, blocked on stdin, and gave the person running it no output and
    no prompt back.
    """
    monkeypatch.setattr(server.sys, "stdin", _ExplodingStdin())
    assert server.main(["--help"]) == 0
    out = capsys.readouterr().out
    assert "usage: optiondesk-mcp" in out
    assert "--version" in out


def test_version_prints_and_exits_without_reading_stdin(monkeypatch,
                                                        capsys):
    monkeypatch.setattr(server.sys, "stdin", _ExplodingStdin())
    assert server.main(["--version"]) == 0
    out = capsys.readouterr().out
    assert server.SERVER_NAME in out
    assert server.__version__ in out


def test_short_flags_work_too(monkeypatch, capsys):
    monkeypatch.setattr(server.sys, "stdin", _ExplodingStdin())
    assert server.main(["-h"]) == 0
    assert "usage: optiondesk-mcp" in capsys.readouterr().out
    assert server.main(["-V"]) == 0
    assert server.__version__ in capsys.readouterr().out


def test_an_unrecognised_argument_does_not_silently_become_a_server(
        monkeypatch, capsys):
    """Falling through to serve() is the worst answer available: the caller
    who mistyped a flag gets a process that looks hung.
    """
    monkeypatch.setattr(server.sys, "stdin", _ExplodingStdin())
    assert server.main(["--no-such-flag"]) == 2
    captured = capsys.readouterr()
    assert "--no-such-flag" in captured.err
    assert captured.out == "", "usage for an error belongs on stderr"


def test_no_argument_still_serves(monkeypatch):
    """The default path is the one an MCP client uses, and it must not have
    been narrowed by the argument handling above it.
    """
    served = []
    monkeypatch.setattr(server, "serve", lambda: served.append(True))
    assert server.main([]) == 0
    assert served == [True]


# ------------------------------------------------------------ 6. recommend

def test_recommend_is_advertised_as_the_type_its_handler_coerces():
    """WHAT WOULD BREAK. recommend was advertised as a string and spent as
    an integer: cli/strategy.py calls int() on it. A schema-validating
    client rejected the integer a model naturally sends for an outlook from
    -2 to +2, and the string that satisfied the schema only worked because
    int() happens to parse "1".

    Both halves are checked, so the pair cannot drift apart again from
    either side.
    """
    tools = server.handle({"jsonrpc": "2.0", "id": 1,
                           "method": "tools/list"})["result"]["tools"]
    build = next(t for t in tools if t["name"] == "option_strategy_build")
    advertised = build["inputSchema"]["properties"]["recommend"]["type"]

    import inspect
    source = inspect.getsource(strategy_cmd.run)
    assert "int(args.recommend)" in source, (
        "the handler no longer coerces recommend with int(); the advertised "
        "type has to follow it")
    assert advertised == "integer"


@needs_engine
def test_an_integer_recommend_is_accepted(desk):
    """The type a schema-validating client will now send has to work."""
    body = body_of(call("option_strategy_build", {"recommend": 1}))
    assert body["outlook"] == 1
    assert body["ranked"]


# ------------------------------------------------- 7. reporting discipline

def test_every_tool_description_carries_the_reporting_rule():
    """WHAT WOULD BREAK. This server is the whole surface Codex and Gemini
    get, and neither loads the skill files that carry the desk's reporting
    discipline. Not one of the ten descriptions told a caller to report the
    degraded flag or to cite the artifact path, so for those two runtimes
    the rule did not exist.
    """
    tools = server.handle({"jsonrpc": "2.0", "id": 1,
                           "method": "tools/list"})["result"]["tools"]
    assert tools
    for tool in tools:
        assert "degraded" in tool["description"], tool["name"]
        assert "artifact path" in tool["description"], tool["name"]
        assert tool["description"].endswith(server.REPORTING_RULE.strip()), (
            tool["name"])


@needs_engine
def test_every_tool_result_carries_the_disclaimer(desk, chain_snapshot):
    """WHAT WOULD BREAK. DISCLAIMER was imported and reached exactly one
    result, option_desk_status, which is the single tool that reports no
    numbers. Every tool a model actually quotes a figure from returned
    nothing to attach that figure to.

    Driven through the tools that complete without a provider, which is
    seven of the ten.
    """
    two_expiry_chains(chain_snapshot, desk)
    for name, arguments in OFFLINE_CALLS:
        response = call(name, arguments)
        assert "error" not in response, (name, response)
        body = body_of(response)
        assert not response["result"].get("isError"), (name, body)
        assert body["disclaimer"] == DISCLAIMER, name


def test_a_handler_that_supplies_its_own_disclaimer_keeps_it(desk):
    """option_desk_status already carried one. Overwriting it would make
    the result frame the authority on a field the handler owns.
    """
    body = body_of(call("option_desk_status", {}))
    assert body["disclaimer"] == DISCLAIMER


def test_an_error_result_is_not_dressed_up_with_a_disclaimer(desk):
    """A failure reports the failure. Attaching the standard footer to it
    would put the language of a finished analysis on something that
    produced no numbers at all.
    """
    response = call("option_greeks_ladder",
                    {"snapshot": "/nonexistent/path.json"})
    body = body_of(response)
    assert response["result"]["isError"] is True
    assert "disclaimer" not in body


def test_non_object_arguments_blame_the_caller_not_the_server():
    """A malformed call is -32602, never -32603.

    A client sending a string where the object belongs used to reach .get()
    and surface as an internal error, which tells a model the server is
    broken and gives it nothing to correct. The distinction matters because
    one of those is the model's to fix and the other is not.
    """
    for bad in ("a string", ["a", "list"], 7):
        response = server.handle({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "option_desk_status", "arguments": bad}})
        assert "error" in response, bad
        assert response["error"]["code"] == -32602, (bad, response["error"])
        assert "object" in response["error"]["message"]
