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

# Numbers are written out in the documentation, so the test has to know how
# to spell them. This was a hand-maintained dictionary and it needed
# extending four times in one afternoon, each time as a test failure saying
# "add 17 to the number words", which is friction with no information in it.
_UNITS = ("zero one two three four five six seven eight nine ten eleven "
          "twelve thirteen fourteen fifteen sixteen seventeen eighteen "
          "nineteen").split()
_TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
         "eighty", "ninety")


def spell(number):
    """A whole number under one hundred, as the documentation writes it."""
    if not 0 <= number < 100:
        raise ValueError("no spelling for {}".format(number))
    if number < 20:
        return _UNITS[number]
    tens, unit = divmod(number, 10)
    return _TENS[tens] + ("-" + _UNITS[unit] if unit else "")


class _Words(dict):
    """Reads like the dictionary it replaced, capitalised as prose needs."""

    def __missing__(self, key):
        return spell(key).capitalize()

    def get(self, key, default=None):
        try:
            return self[key]
        except ValueError:
            return default


WORDS = _Words()


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
    word = spell(n)
    readme = read("README.md")
    assert "{} mutations".format(word) in readme, (
        "README does not say the harness has {} mutations".format(n))
    assert "{} breakages".format(word) in read("docs/CAPABILITIES.md"), (
        "CAPABILITIES does not say the harness has {} breakages".format(n))


def _rendered_dashboard():
    """The page as a viewer gets it, from whatever artifacts are on disk."""
    from optiondesk.dashboard import app

    return app.render_index()


def test_the_dashboard_counts_are_written_correctly():
    """Panels and canvases, counted from the rendered page.

    These went stale silently once already: four charts shipped and the
    documented figures still said twenty-eight canvases across thirty-five
    panels, with nothing to catch it because no test looked at the page at
    all. The count is a ceiling, so a machine holding fewer artifacts than
    the documented maximum is not a failure; a page rendering MORE than the
    documentation claims is.
    """
    html = _rendered_dashboard()
    canvases = len(re.findall(r"id='[a-zA-Z0-9_-]+' class='chart", html))
    panels = len(re.findall(r"class='panel", html))
    capabilities = read("docs/CAPABILITIES.md")

    documented = re.search(
        r"([A-Za-z-]+) panels and, at most, ([a-z-]+) chart canvases",
        capabilities)
    assert documented, (
        "docs/CAPABILITIES.md no longer states the panel and canvas counts")
    said_panels, said_canvases = documented.group(1), documented.group(2)

    assert canvases <= _number(said_canvases), (
        "the page rendered {} canvases and the documentation claims at most "
        "{}".format(canvases, said_canvases))
    assert panels <= _number(said_panels), (
        "the page rendered {} panels and the documentation claims {}".format(
            panels, said_panels))

    # And the ceiling must not drift far above what anything can reach, or
    # it stops being a statement about the software.
    if canvases:
        assert _number(said_canvases) - canvases <= 6, (
            "the documented ceiling of {} is well above the {} this desk "
            "can render; one of the two is wrong".format(
                said_canvases, canvases))


def _number(word):
    """Turn a written number back into an integer, for reading prose."""
    word = word.lower().strip()
    for value in range(0, 100):
        if spell(value) == word:
            return value
    raise AssertionError("cannot read the number {!r}".format(word))


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


def test_the_install_path_count_matches_the_numbered_sections():
    """INSTALL.md is numbered by hand, so the count and the sections drift.

    Adding the skills CLI as a path renumbered four sections and left three
    cross references pointing at the wrong ones. The count in the opening
    line, in the README's documentation map and in CAPABILITIES all have to
    agree with how many numbered sections the file actually has.
    """
    install = read("INSTALL.md")
    sections = re.findall(r"^## (\d+)\. ", install, re.M)
    assert sections, "INSTALL.md has no numbered sections"
    assert [int(s) for s in sections] == list(range(1, len(sections) + 1)), (
        "the numbered sections are {} rather than consecutive from 1".format(
            sections))

    n = len(sections)
    word = spell(n)
    assert "{} ways in".format(word.capitalize()) in install, (
        "INSTALL.md opens claiming a different number than its {} "
        "sections".format(n))
    assert "{} install paths".format(word) in read("README.md"), (
        "the README documentation map disagrees with INSTALL.md")
    assert "{} paths, each verified".format(word.capitalize()) in read(
        "docs/CAPABILITIES.md"), (
        "docs/CAPABILITIES.md disagrees with INSTALL.md")
