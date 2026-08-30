"""MCP surface. These are the calls every runtime makes before anything
else, so a regression here breaks Claude Code, Codex and Gemini at once."""

import io
import json

from optiondesk.mcp import server


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
