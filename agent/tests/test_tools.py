"""The desk commands as LangChain tools.

Building a tool does not call its runner, so nothing here reaches a
provider. The one test that invokes a tool substitutes the spec first.
"""

import pytest
from langchain_core.tools import StructuredTool

from optiondesk_agent import tools as tools_module
from optiondesk_agent.tools import SPECS, _Args, desk_tools, tool_specs


def fake_spec(seen, public=("symbol", "expiry"), defaults=None):
    """A spec whose runner records the namespace it was handed."""
    def runner(args):
        seen["symbol"] = getattr(args, "symbol", "<<absent>>")
        seen["expiry"] = getattr(args, "expiry", "<<absent>>")
        seen["out_dir"] = getattr(args, "out_dir", "<<absent>>")
        seen["rejected"] = list(args.rejected)
        return {"artifact": "nowhere.json"}

    return {
        "name": "option_chain_snapshot",
        "description": "a test double",
        "runner": runner,
        "defaults": defaults or {"symbol": None, "expiry": None,
                                 "out_dir": None},
        "public": public,
    }


# --------------------------------------------------------------------------
# What desk_tools builds.
# --------------------------------------------------------------------------

def test_every_spec_becomes_a_structured_tool_with_its_own_name():
    """Catches a tool renamed, dropped, or built as the wrong class.

    The name is the only handle a model has on a capability. A tool whose
    name drifts from its spec is a capability the router prompt advertises
    and the agent cannot call.
    """
    tools = desk_tools()

    assert len(tools) == len(SPECS)
    assert all(isinstance(tool, StructuredTool) for tool in tools)
    assert [tool.name for tool in tools] == [spec["name"] for spec in SPECS]


def test_descriptions_survive_onto_the_tool():
    """Catches a tool shipped with an empty or generated description.

    The description carries the caveats: delayed data, modelled premiums,
    the positioning assumption. A model choosing between tools on names
    alone loses every one of them.
    """
    for spec, tool in zip(SPECS, desk_tools()):
        assert tool.description == spec["description"]
        assert len(tool.description) > 40


def test_include_narrows_the_surface():
    """Catches include being ignored, which hands over the whole desk.

    A read only assistant given the forward test tool can open and close
    paper positions. The narrowing is the safety property.
    """
    tools = desk_tools(include=["option_expiries", "option_greeks_ladder"])

    assert sorted(tool.name for tool in tools) == ["option_expiries",
                                                   "option_greeks_ladder"]


def test_an_unknown_include_name_yields_no_tools():
    """Catches a typo in include silently returning the full set.

    Failing open here is the dangerous direction: the caller believes they
    restricted the surface and did not.
    """
    assert desk_tools(include=["option_not_a_real_tool"]) == []


# --------------------------------------------------------------------------
# The schema an agent actually sees.
# --------------------------------------------------------------------------

def test_every_tool_advertises_its_declared_public_parameters():
    """Catches the tool schema collapsing to one opaque parameter.

    This is the regression guard for a shipped defect: the wrapper takes
    **kwargs, and LangChain builds the schema from the signature, so left
    bare the schema exposed a single object called kwargs. No parameter was
    named to the model and no supplied argument survived validation.
    """
    for spec, tool in zip(SPECS, desk_tools()):
        assert list(tool.args) == list(spec["public"]), tool.name


def test_no_tool_advertises_the_output_directory():
    """Catches out_dir reaching the schema and becoming model-settable.

    out_dir decides where an artifact lands. A model that can choose it can
    write outside the artifact directory the rest of the desk reads.
    """
    for tool in desk_tools():
        assert "out_dir" not in tool.args


def test_tool_specs_matches_what_the_tools_advertise():
    """Catches the LangChain-free view drifting from the LangChain one.

    tool_specs exists so a caller without LangChain sees the same surface.
    Two descriptions of one capability that disagree is worse than one.
    """
    specs = {spec["name"]: spec["parameters"] for spec in tool_specs()}
    tools = {tool.name: list(tool.args) for tool in desk_tools()}

    assert specs == tools


# --------------------------------------------------------------------------
# Invocation delivers the arguments.
# --------------------------------------------------------------------------

def test_invoking_a_tool_delivers_the_supplied_arguments(monkeypatch):
    """Catches arguments being dropped between invoke and the runner.

    This is the behaviour the schema defect actually broke: the call
    returned a clean result while the runner ran on defaults, so a request
    for an SPY chain fetched nothing and reported success.
    """
    seen = {}
    monkeypatch.setattr(tools_module, "SPECS", [fake_spec(seen)])
    tool = desk_tools()[0]

    tool.invoke({"symbol": "SPY", "expiry": "2026-09-18"})

    assert seen["symbol"] == "SPY"
    assert seen["expiry"] == "2026-09-18"


def test_an_omitted_argument_arrives_as_its_declared_default(monkeypatch):
    """Catches a default going missing and the runner seeing no attribute.

    The runners read args.expiry unconditionally. An absent attribute is an
    AttributeError inside the command rather than a clear argument error.
    """
    seen = {}
    monkeypatch.setattr(tools_module, "SPECS", [fake_spec(seen)])

    desk_tools()[0].invoke({"symbol": "SPY"})

    assert seen["expiry"] is None
    assert seen["out_dir"] is None


def test_the_output_directory_cannot_be_reached_through_a_tool(monkeypatch):
    """Catches a caller steering the artifact into a directory of its own.

    out_dir is declared but not public. Supplying it must leave the runner
    on the default, whether it is filtered by the schema or by the shim.
    """
    seen = {}
    monkeypatch.setattr(tools_module, "SPECS", [fake_spec(seen)])

    desk_tools()[0].invoke({"symbol": "SPY", "out_dir": "/tmp/elsewhere"})

    assert seen["out_dir"] is None


# --------------------------------------------------------------------------
# The argument shim.
# --------------------------------------------------------------------------

def test_the_shim_rejects_an_undeclared_key_rather_than_setting_it():
    """Catches the shim passing unknown keys straight onto the namespace.

    Silently accepting them is how a caller reaches a runner argument the
    tool never advertised. The key must be recorded as rejected and must
    not appear on the namespace at all.
    """
    args = _Args({"symbol": None}, {"symbol": "SPY", "out_dir": "/tmp/x"})

    assert args.rejected == ["out_dir"]
    assert not hasattr(args, "out_dir")
    assert args.symbol == "SPY"


def test_the_shim_reports_every_undeclared_key_not_just_the_first():
    """Catches a shim that stops at the first rejection.

    A partial list tells the caller one argument was ignored when three
    were, so they fix one and re-run into the same silence.
    """
    args = _Args({"symbol": None}, {"a": 1, "b": 2, "c": 3})

    assert sorted(args.rejected) == ["a", "b", "c"]


def test_the_shim_applies_declared_defaults_when_nothing_is_supplied():
    """Catches defaults being skipped when the caller supplies nothing.

    Every runner reads its arguments as attributes, so a namespace built
    from an empty call still has to carry the full declared set.
    """
    args = _Args({"band": 0.10, "type": "both"}, {})

    assert args.band == 0.10
    assert args.type == "both"
    assert args.rejected == []


def test_the_shim_accepts_a_supplied_none():
    """Catches None being treated as absent and quietly replaced.

    Several defaults are None and mean "let the command decide". A caller
    passing None explicitly must not be overridden by a truthiness test.
    """
    args = _Args({"expiry": "2026-09-18"}, {"expiry": None})

    assert args.expiry is None


def test_the_shim_tolerates_no_supplied_mapping():
    """Catches a None payload raising instead of falling back to defaults."""
    args = _Args({"symbol": None}, None)

    assert args.symbol is None
    assert args.rejected == []


# --------------------------------------------------------------------------
# The spec table itself.
# --------------------------------------------------------------------------

def test_every_public_parameter_has_a_declared_default():
    """Catches a spec advertising a parameter the shim will reject.

    The shim only honours keys present in defaults, so a public name absent
    from defaults is a parameter the schema offers and the shim discards.
    """
    for spec in SPECS:
        missing = [key for key in spec["public"]
                   if key not in spec["defaults"]]
        assert missing == [], (spec["name"], missing)


def test_tool_names_are_unique():
    """Catches two specs sharing a name, which silently shadows one tool."""
    names = [spec["name"] for spec in SPECS]

    assert len(names) == len(set(names))


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s["name"])
def test_no_spec_exposes_the_output_directory(spec):
    """Catches out_dir being promoted into a spec's public tuple."""
    assert "out_dir" not in spec["public"]
