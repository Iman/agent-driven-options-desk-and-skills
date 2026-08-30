"""The printed summary must carry degradation, not only the artifact.

WHAT WOULD BREAK. Every command writes a `degraded` flag into the artifact
envelope, and five of them used to print a summary with no trace of it. A
reader of standard output, an MCP client holding the tool result, or a
graph node deciding whether to continue could not tell that the numbers it
was about to quote came from a fallback provider or a stale chain. The
reporting rule every skill states, say it is degraded before quoting any
number from it, was unenforceable for those commands because the flag never
reached the reader.

This is checked statically rather than by running the commands, because
degradation needs a provider to fail and a test that needs a provider to
fail is a test that does not run.
"""

import ast
import pathlib

CLI = pathlib.Path(__file__).resolve().parent.parent / "src" / "optiondesk" \
    / "cli"

# Commands whose result cannot be degraded: they touch no provider and read
# no artifact. Listed by name so that adding a command forces a decision
# rather than silently joining the exempt set.
NO_UPSTREAM = {"keys", "__init__", "__main__", "forward"}


def _run_function(tree):
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "run":
            return node
    return None


def _summary_keys(node):
    keys = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Return) and isinstance(sub.value, ast.Dict):
            keys |= {k.value for k in sub.value.keys
                     if isinstance(k, ast.Constant)}
    return keys


def _sets_degraded_in_envelope(tree):
    """True if the module writes a degraded flag into an artifact."""
    for sub in ast.walk(tree):
        if isinstance(sub, ast.keyword) and sub.arg == "degraded":
            return True
    return False


def test_every_command_that_can_degrade_says_so_in_its_summary():
    missing = []
    for path in sorted(CLI.glob("*.py")):
        if path.stem in NO_UPSTREAM:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        run = _run_function(tree)
        if run is None:
            continue
        keys = _summary_keys(run)
        if not keys:
            continue
        if "degraded" not in keys:
            missing.append(path.stem)
    assert not missing, (
        "these commands write a degraded flag into the artifact but omit it "
        "from the summary a caller actually reads: {}".format(missing))


def test_a_degraded_summary_carries_its_reason():
    """A flag with no reason tells a reader to distrust everything equally."""
    for path in sorted(CLI.glob("*.py")):
        if path.stem in NO_UPSTREAM:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        run = _run_function(tree)
        if run is None:
            continue
        keys = _summary_keys(run)
        if "degraded" in keys:
            assert "degraded_reason" in keys, (
                "{} reports degraded without a reason".format(path.stem))


def test_the_exempt_list_is_not_a_place_to_hide():
    """Anything exempt must genuinely have no upstream to degrade."""
    for name in NO_UPSTREAM:
        path = CLI / "{}.py".format(name)
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assert not _sets_degraded_in_envelope(tree), (
            "{} is on the exempt list but writes a degraded flag into an "
            "artifact, so it has an upstream after all".format(name))


# --------------------------------------------------------------- per path

# The static check above unions the keys across every return statement in a
# command, so it proves that at least one path carries the flag rather than
# that all of them do. Two paths in `strategy` answer without building
# anything, and both read a snapshot to reach that answer, so a caller can
# be told a structure was not viable without being told the chain it was
# judged against was degraded. These exercise those paths directly.

def test_the_not_built_path_still_reports_a_degraded_snapshot(monkeypatch,
                                                              tmp_path):
    import json

    from optiondesk.cli import strategy as strategy_cmd

    snapshot = {
        "meta": {"degraded": True,
                 "degraded_reason": "provider fell back",
                 "provider_used": "stub", "notes": []},
        "underlying": "TEST", "spot": 100.0, "expiry": "2026-09-18",
        "days_to_expiry": 21.0, "risk_free_rate": 0.04,
        "dividend_yield": 0.0, "contracts": [],
        "counts": {"with_iv": 0, "without_iv": 0},
    }
    path = tmp_path / "chain_TEST_2026-09-18.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")

    # The engine returning None is the "nothing viable" outcome. Forcing it
    # keeps this about the reporting path rather than about which chains
    # happen to admit a condor.
    strategies = strategy_cmd.engine_bridge.strategies()
    monkeypatch.setattr(strategies, "build", lambda *a, **k: None)

    class Args:
        name = "iron_condor"
        snapshot = str(path)
        far_snapshot = None
        kind = "call"
        offset = 0.03
        size = 1.0
        underlying_entry = None
        out_dir = str(tmp_path)
        list_only = False
        recommend = None
        vol_view = None
        owns_underlying = False
        direction_unknown = False

    result = strategy_cmd.run(Args())
    assert result["built"] is False
    assert result["degraded"] is True, (
        "a structure judged against a degraded chain was reported without "
        "saying the chain was degraded")
    assert result["degraded_reason"] == "provider fell back"
