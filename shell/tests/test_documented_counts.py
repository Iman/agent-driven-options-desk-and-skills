"""Numbers written in the documentation must match what is in the tree.

WHAT WOULD BREAK. Every count in this project's documentation was wrong at
least once: seven schemas when there were eight, eleven structures when
there were fourteen, two packages when there were three, seven refresh
stages when a full run has eight, and three separate test counts that
rotted inside a single afternoon. None of it was caught by review, because
a stale number reads exactly like a fresh one.

So the numbers are measured here and the documented phrasing is built from
the measurement. Change the thing being counted without changing the
sentence and this fails, naming the file and the phrase it expected.

It does not check every number in the docs. Counts derived from live market
data cannot be pinned this way, and are marked in the documents themselves
as examples rather than invariants.
"""

import ast
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
SHELL = ROOT / "shell"

WORDS = {
    2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six", 7: "Seven",
    8: "Eight", 9: "Nine", 10: "Ten", 11: "Eleven", 12: "Twelve",
    14: "Fourteen", 16: "Sixteen",
}


def read(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


# ----------------------------------------------------------- measurements

def count_schemas():
    return len(list((SHELL / "src" / "optiondesk" / "contracts")
                    .glob("*.schema.json")))


def count_structures():
    source = (ROOT / "engine" / "src" / "optiondesk_engine" / "strategies"
              / "playbook.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "PLAYBOOK":
                    return len(node.value.keys)
    raise AssertionError("PLAYBOOK not found")


def count_mcp_tools():
    source = (SHELL / "src" / "optiondesk" / "mcp"
              / "server.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "TOOLS":
                    return len(node.value.elts)
    raise AssertionError("TOOLS not found")


def count_langchain_tools():
    source = (ROOT / "agent" / "src" / "optiondesk_agent"
              / "tools.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "SPECS":
                    return len(node.value.elts)
    raise AssertionError("SPECS not found")


def count_cli_commands():
    from optiondesk.cli import __main__ as dispatcher

    parser = dispatcher.build_parser()
    for action in parser._actions:
        if getattr(action, "choices", None) and hasattr(action.choices,
                                                        "keys"):
            return len(action.choices)
    raise AssertionError("no subparsers found")


def count_refresh_stages():
    """Stages a full run executes, expanding the loop over the suites."""
    source = (ROOT / "scripts" / "refresh.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = [node for node in ast.walk(tree)
             if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Name)
             and node.func.id == "stage"]
    suites = [name for name in re.findall(r'"([a-z]+/tests)"', source)]
    # One call site sits inside the loop over the suites, so it accounts for
    # as many stages as there are suites that exist.
    present = [s for s in dict.fromkeys(suites) if (ROOT / s).exists()]
    return len(calls) - 1 + len(present)


def collected(suite):
    """How many tests pytest collects, which is what a reader will see."""
    finished = subprocess.run(
        [sys.executable, "-m", "pytest", suite, "--collect-only", "-q",
         "--no-header", "-p", "no:cacheprovider"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300)
    match = re.search(r"(\d+) tests? collected", finished.stdout)
    if not match:
        match = re.search(r"(\d+)/(\d+) tests collected", finished.stdout)
        if match:
            return int(match.group(1))
        raise AssertionError(
            "could not read a collection count from: {}".format(
                finished.stdout[-400:]))
    return int(match.group(1))


# ------------------------------------------------------------ the claims

def test_schema_count_is_written_correctly():
    n = count_schemas()
    assert "{} schemas under".format(WORDS[n]) in read("README.md")
    assert "{} JSON schemas".format(WORDS[n]) in read("docs/CAPABILITIES.md")
    assert "{} schemas + validator".format(n) in read("README.md")


def test_structure_count_is_written_correctly():
    n = count_structures()
    assert "{} structures".format(WORDS[n]) in read("docs/CAPABILITIES.md")
    assert "all fourteen structures" in read(
        "shell/skills/options-strategy/SKILL.md") or n != 14


def test_tool_counts_are_written_correctly():
    mcp = count_mcp_tools()
    assert "{} tools".format(mcp) in read("README.md")
    assert "{}, over stdio".format(WORDS[mcp]) in read("docs/CAPABILITIES.md")
    assert "{} tools".format(WORDS[mcp]) in read("INSTALL.md")

    chain = count_langchain_tools()
    assert "{} `StructuredTool`".format(
        WORDS[chain].lower()) in read("docs/CAPABILITIES.md")


def test_surface_counts_are_written_correctly():
    skills = len(list((SHELL / "skills").glob("*/SKILL.md")))
    commands = len(list((ROOT / ".claude" / "commands").glob("*.md")))
    agents = len(list((ROOT / ".claude" / "agents").glob("*.md")))
    capabilities = read("docs/CAPABILITIES.md")
    assert "{} skills".format(WORDS[skills]) in capabilities
    assert "{}, in `.claude/commands/`".format(
        WORDS[commands]) in capabilities
    assert "{}, in `.claude/agents/`".format(WORDS[agents]) in capabilities


def test_cli_command_count_is_written_correctly():
    n = count_cli_commands()
    assert "{} commands".format(WORDS[n]) in read("docs/CAPABILITIES.md")


def test_refresh_stage_count_is_written_correctly():
    n = count_refresh_stages()
    phrase = "{} stages in a full run".format(WORDS[n])
    assert phrase in read("README.md"), phrase
    assert phrase in read("docs/CAPABILITIES.md"), phrase


def test_the_readme_quotes_the_real_test_counts():
    """The three numbers in the development section, as pytest reports them.

    These are the ones that rotted fastest, because every commit that adds
    a test invalidates them and nothing complained.
    """
    readme = read("README.md")
    for suite, label in (("engine/tests", "engine"), ("shell/tests", "shell"),
                         ("agent/tests", "agent")):
        if not (ROOT / suite).exists():
            continue
        n = collected(suite)
        assert re.search(r"pytest {} -q\s+# {} tests".format(
            re.escape(suite), n), readme), (
            "README does not say {} has {} tests".format(suite, n))


def count_mutations():
    source = (ROOT / "scripts" / "mutate.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "MUTATIONS":
                    return len(node.value.elts)
    raise AssertionError("MUTATIONS not found")


def test_the_mutation_count_is_written_correctly():
    """The harness grows with every fix, so its documented size moves."""
    n = count_mutations()
    words = dict(WORDS)
    words.update({13: "thirteen", 15: "fifteen", 16: "sixteen",
                  17: "seventeen", 18: "eighteen", 19: "nineteen",
                  21: "twenty-one", 22: "twenty-two"})
    word = words.get(n)
    assert word, "add {} to the number words in this test".format(n)
    readme = read("README.md")
    assert "{} mutations".format(word) in readme, (
        "README does not say the harness has {} mutations".format(n))
    assert "{} breakages".format(word) in read("docs/CAPABILITIES.md"), (
        "CAPABILITIES does not say the harness has {} breakages".format(n))


def test_the_marketplace_manifest_matches_what_is_packaged():
    """The plugin is generated, so its manifest must not be edited by hand."""
    manifest = json.loads(read(".claude-plugin/marketplace.json"))
    assert manifest["plugins"], "no plugins declared"
    plugin = ROOT / "plugin"
    if not plugin.exists():
        return
    assert len(list((plugin / "skills").glob("*/SKILL.md"))) == len(
        list((SHELL / "skills").glob("*/SKILL.md")))
    assert len(list((plugin / "commands").glob("*.md"))) == len(
        list((ROOT / ".claude" / "commands").glob("*.md")))


def test_the_plugin_is_not_stale_against_its_sources():
    """A copied file drifts; a symlinked one cannot.

    Skills reach the plugin by copy, and so do commands and agents. During
    one audit two command files in plugin/ were older than their sources,
    and nothing failed. Anyone installing the plugin in that window would
    have got the previous instructions with no sign that they were not the
    current ones.
    """
    plugin = ROOT / "plugin"
    if not plugin.exists():
        return
    stale = []
    for source_dir, name in ((SHELL / "skills", "skills"),
                             (ROOT / ".claude" / "commands", "commands"),
                             (ROOT / ".claude" / "agents", "agents")):
        if not source_dir.exists():
            continue
        for source in sorted(source_dir.rglob("*")):
            if source.is_dir() or source.name in (
                    ".installed-by-optiondesk",) or "__pycache__" in str(
                    source):
                continue
            copied = plugin / name / source.relative_to(source_dir)
            if not copied.exists():
                stale.append("{} is missing from the plugin".format(
                    source.relative_to(ROOT)))
            elif copied.read_bytes() != source.read_bytes():
                stale.append("{} differs from {}".format(
                    copied.relative_to(ROOT), source.relative_to(ROOT)))
    assert not stale, (
        "the plugin is out of date. Run python3 scripts/package.py. "
        + "; ".join(stale[:5]))
