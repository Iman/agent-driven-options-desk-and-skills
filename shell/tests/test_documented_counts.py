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
    plugin = ROOT / "plugins" / "option-desk"
    if not plugin.exists():
        return
    assert len(list((plugin / "skills").glob("*/SKILL.md"))) == len(
        list((SHELL / "skills").glob("*/SKILL.md")))
    assert len(list((plugin / "commands").glob("*.md"))) == len(
        list((ROOT / ".claude" / "commands").glob("*.md")))


def test_the_plugin_is_not_stale_against_its_sources():
    """A copied file drifts; a symlinked one cannot.

    Skills reach the plugin by copy, and so do commands and agents. During
    one audit two command files in the bundle were older than their
    sources,
    and nothing failed. Anyone installing the plugin in that window would
    have got the previous instructions with no sign that they were not the
    current ones.
    """
    plugin = ROOT / "plugins" / "option-desk"
    if not plugin.exists():
        return
    stale = []
    for source_dir, name in ((SHELL / "skills", "skills"),
                             (ROOT / ".claude" / "commands", "commands"),
                             (ROOT / ".claude" / "agents", "agents")):
        if not source_dir.exists():
            continue
        for source in sorted(source_dir.rglob("*")):
            if (source.is_dir()
                    or source.name in (".installed-by-optiondesk", ".DS_Store")
                    or "__pycache__" in str(source)):
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


def test_every_package_carries_the_licence_it_declares():
    """A published package whose licence is only in prose is a problem.

    The repository is dual licensed, and the root had no LICENSE file at
    all, so GitHub showed none and a visitor could not tell what applied to
    what. The agent package declared MIT in its metadata and shipped no
    licence text.
    """
    # One licence over the whole repository since 2026-08-31. The earlier
    # MIT and AGPL split permitted the commercial use it was meant to
    # prevent.
    expected = {
        "engine": ("PolyForm-Noncommercial-1.0.0", "POLYFORM NONCOMMERCIAL"),
        "shell": ("PolyForm-Noncommercial-1.0.0", "POLYFORM NONCOMMERCIAL"),
        "agent": ("PolyForm-Noncommercial-1.0.0", "POLYFORM NONCOMMERCIAL"),
    }
    for package, (declared, in_text) in expected.items():
        directory = ROOT / package
        if not directory.exists():
            continue
        licence = directory / "LICENSE"
        assert licence.exists(), (
            "{} declares {} and ships no LICENSE file".format(package,
                                                              declared))
        assert in_text in licence.read_text(encoding="utf-8").upper(), (
            "{}/LICENSE does not look like {}".format(package, declared))

        pyproject = directory / "pyproject.toml"
        if pyproject.exists():
            text = pyproject.read_text(encoding="utf-8")
            assert declared in text, (
                "{}/pyproject.toml does not declare {}".format(package,
                                                              declared))

    root_licence = ROOT / "LICENSE"
    assert root_licence.exists(), (
        "the repository root has no LICENSE, so GitHub shows none at all")

    # One licence covers the whole repository, so every copy must be
    # identical. When they differed, the root file had to explain the split
    # instead; a repository where two LICENSE files disagree is worse than
    # one with a single file, because the reader cannot tell which governs.
    root_text = root_licence.read_text(encoding="utf-8")
    for package in expected:
        directory = ROOT / package
        if not directory.exists():
            continue
        assert (directory / "LICENSE").read_text(encoding="utf-8") == \
            root_text, (
            "{}/LICENSE differs from the root LICENSE".format(package))

    assert "Required Notice:" in root_text, (
        "the licence carries no Required Notice, which is the clause that "
        "makes attribution travel with a copy")
    assert "noncommercial" in root_text.lower()


def test_every_repository_named_as_an_influence_states_its_licence():
    """An acknowledgement without terms is not an acknowledgement.

    THIRD-PARTY.md names other people's work, and the point of naming it
    is that a reader can tell what they are allowed to do. An entry that
    gives a project name and no licence leaves them worse off than no
    entry, because it implies the question was considered.
    """
    text = read("THIRD-PARTY.md")
    section = text.split("## Referenced for ideas", 1)
    assert len(section) == 2, "the acknowledgements section is gone"
    body = section[1].split("\n## ", 1)[0]

    # An entry runs from its bullet to the next one, not to the end of the
    # line: these are wrapped prose, and the licence often lands on the
    # continuation. Reading one line only reported a false gap.
    entries = [e for e in re.split(r"\n(?=- `)", body.strip())
               if e.startswith("- `")]
    assert entries, "no acknowledgements found"

    silent = []
    for entry in entries:
        name = re.match(r"- `([^`]+)`", entry).group(1)
        licensed = re.search(
            r"MIT|Apache|GPL|BSD|ODC|no licence|not used|Unlicense", entry,
            re.I)
        if not licensed:
            silent.append(name)
    assert not silent, (
        "these are named without saying what their licence is: "
        "{}".format(silent))


def test_both_hosts_can_find_the_plugin_and_the_skills():
    """One bundle, two manifests, and a discovery path for each runtime.

    Claude Code reads .claude-plugin/marketplace.json and loads skills from
    .claude/skills. Codex and ChatGPT read .agents/plugins/marketplace.json
    and scan .agents/skills, verified against OpenAI's documentation. Both
    marketplaces have to point at the same bundle, and both discovery paths
    have to reach the same five skills, or one host silently gets less than
    the other.
    """
    bundle = ROOT / "plugins" / "option-desk"
    assert (bundle / ".claude-plugin" / "plugin.json").exists(), (
        "the bundle has no Claude manifest")
    assert (bundle / ".codex-plugin" / "plugin.json").exists(), (
        "the bundle has no Codex manifest, so ChatGPT and Codex cannot "
        "install it")

    for marketplace, key in ((".claude-plugin/marketplace.json", "source"),
                             (".agents/plugins/marketplace.json", "source")):
        manifest = json.loads(read(marketplace))
        entry = manifest["plugins"][0]
        source = entry[key]
        path = source if isinstance(source, str) else source["path"]
        assert (ROOT / path).is_dir(), (
            "{} points at {}, which is not a directory".format(marketplace,
                                                               path))
        assert path.endswith("option-desk"), (
            "{} points somewhere other than the bundle".format(marketplace))

    # Both discovery paths, and they must agree.
    claude = {p.parent.name for p in (SHELL / "skills").glob("*/SKILL.md")}
    codex = {p.parent.name
             for p in (ROOT / ".agents" / "skills").glob("*/SKILL.md")}
    assert codex == claude, (
        "the two runtimes see different skills: Codex {}, Claude {}".format(
            sorted(codex), sorted(claude)))
    assert codex, "no skills are discoverable at all"


def test_every_skill_points_at_a_disclaimer_that_travels_with_it():
    """A pointer to a file the reader does not have is worse than none.

    The skills are installed standalone, uploaded as zips, and bundled into
    a plugin. A reference to the repository root resolves in exactly one of
    those cases.
    """
    import zipfile

    for skill in sorted((SHELL / "skills").glob("*/SKILL.md")):
        assert "DISCLAIMER.md" in skill.read_text(encoding="utf-8"), (
            "{} points at no disclaimer".format(skill.parent.name))

    dist = ROOT / "dist" / "skills"
    if not dist.exists():
        return
    for archive in sorted(dist.glob("*.zip")):
        with zipfile.ZipFile(archive) as zipped:
            names = zipped.namelist()
        assert any(n.endswith("DISCLAIMER.md") for n in names), (
            "{} references a disclaimer it does not carry".format(
                archive.name))


def test_the_readme_contents_list_names_every_section():
    """A table of contents that omits a section is worse than none.

    Two sections added in one afternoon, Usage and Asset classes, never
    reached the list. A reader scanning it concludes the document does not
    cover them.
    """
    text = read("README.md")
    body = text.split("## Contents", 1)[1].split("\n---", 1)[0]
    listed = set(re.findall(r"^- \[([^\]]+)\]", body, re.M))
    actual = [h for h in re.findall(r"^## (.+)$", text, re.M)
              if h != "Contents"]

    missing = [h for h in actual if h not in listed]
    assert not missing, (
        "these sections are in the README and not in its contents "
        "list: {}".format(missing))

    phantom = [h for h in listed if h not in actual]
    assert not phantom, (
        "the contents list names sections that do not exist: {}".format(
            phantom))


def test_the_documented_dashboard_port_is_the_real_default():
    """A port a reader types and cannot reach is a bad first impression."""
    import ast

    source = (SHELL / "src" / "optiondesk" / "cli"
              / "__main__.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    default = None
    for node in ast.walk(tree):
        if (isinstance(node, ast.keyword) and node.arg == "default"
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, int)
                and 1024 < node.value.value < 65536):
            default = node.value.value
            break
    assert default, "no dashboard port default found in the parser"

    for name in ("README.md", "INSTALL.md", "FAQ.md"):
        for line in read(name).splitlines():
            if "optiondesk dashboard" in line and "127.0.0.1:" in line:
                assert str(default) in line or "--port" in line, (
                    "{} shows `{}` without --port, but the default is "
                    "{}".format(name, line.strip(), default))


def test_no_document_recommends_scheduling_the_desk_in_the_cloud():
    """`/schedule` creates a cloud agent. This desk is local.

    WHAT WOULD BREAK. Claude Code's /schedule builds a scheduled agent that
    runs on Anthropic's infrastructure. It cannot see `optiondesk` in
    ~/.local/bin, the virtualenv under ~/.optiondesk, or any artifact in
    ~/TradingDesk. Four documents recommended scheduling `/desk-watch` and
    `/desk-complete` that way, which produces a routine that wakes up
    somewhere with none of the desk and nothing to compare against.

    Mentioning /schedule is fine, and two documents now explain exactly
    this. Putting a desk command after it is not.
    """
    import re

    offenders = []
    for name in ("README.md", "FAQ.md", "LOOPS.md", "docs/CAPABILITIES.md"):
        for number, line in enumerate(read(name).splitlines(), 1):
            if "/schedule" not in line:
                continue
            after = line.split("/schedule", 1)[1]
            if re.search(r"/desk-|optiondesk ", after):
                offenders.append("{}:{}: {}".format(name, number,
                                                    line.strip()[:70]))

    commands = ROOT / ".claude" / "commands"
    for path in sorted(commands.glob("*.md")):
        for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), 1):
            if "/schedule" in line and re.search(
                    r"/desk-|optiondesk ", line.split("/schedule", 1)[1]):
                offenders.append("{}:{}".format(path.name, number))

    assert not offenders, (
        "these tell the reader to schedule a local desk command as a cloud "
        "agent: {}".format(offenders))


def test_commands_use_named_arguments_not_indexed_ones():
    """Indexed placeholders were off by one and silently stayed literal.

    Claude Code documents `$N` as `$ARGUMENTS[N]`, zero based, so `$0` is
    the first argument and `$1` the second. Every command here used `$1`
    for the symbol, and an indexed placeholder with no matching argument
    "stays in the content unchanged", so `/desk-open SPY` put a literal
    `$1` in front of the model.

    Named arguments declared in frontmatter map to positions in order, so
    the mistake cannot be made again.
    """
    import re

    commands = ROOT / ".claude" / "commands"
    problems = []
    for path in sorted(commands.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        indexed = re.findall(r"\$\{?\d", text)
        if indexed:
            problems.append("{} still uses {}".format(path.name,
                                                      sorted(set(indexed))))
            continue

        head = text.split("---", 2)[1] if text.startswith("---") else ""
        declared = re.search(r"^arguments:\s*\[([^\]]*)\]", head, re.M)
        names = ([n.strip() for n in declared.group(1).split(",") if n.strip()]
                 if declared else [])
        used = set(re.findall(r"\$([a-z][a-z_]*)", text))
        # Shell variables the body defines itself are not skill arguments.
        used -= set(re.findall(r"^([A-Za-z_]+)=", text, re.M))
        used -= {"desk", "sym", "home"}
        unknown = [u for u in used if u not in names]
        if unknown:
            problems.append("{} uses {} which it does not declare".format(
                path.name, sorted(unknown)))

    assert not problems, problems


def test_the_argument_hint_matches_the_declared_arguments():
    """The hint is what autocomplete shows. It has to be the truth."""
    import re

    for path in sorted((ROOT / ".claude" / "commands").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        head = text.split("---", 2)[1] if text.startswith("---") else ""
        hint = re.search(r"^argument-hint:\s*(.+)$", head, re.M)
        declared = re.search(r"^arguments:\s*\[([^\]]*)\]", head, re.M)
        if not hint or not declared:
            continue
        names = [n.strip() for n in declared.group(1).split(",") if n.strip()]
        shown = re.findall(r"[A-Za-z_]+", hint.group(1))
        assert len(shown) == len(names), (
            "{}: the hint shows {} and the command declares {}".format(
                path.name, shown, names))


def test_the_community_files_github_turns_into_tabs_all_exist():
    """GitHub renders a tab strip from five specific root files.

    README.md, LICENSE, SECURITY.md, CODE_OF_CONDUCT.md and CONTRIBUTING.md.
    A missing one is a missing tab, and the repository looks less cared for
    than it is.
    """
    for name in ("README.md", "LICENSE", "SECURITY.md",
                 "CODE_OF_CONDUCT.md", "CONTRIBUTING.md"):
        path = ROOT / name
        assert path.exists(), "{} is missing, so its tab will not appear".format(name)
        assert len(path.read_text(encoding="utf-8").split()) > 80, (
            "{} is too thin to be worth a tab".format(name))


def test_the_privacy_rule_is_stated_where_it_will_be_read():
    """A rule only in the code of conduct is a rule nobody reads in time.

    Someone whose install failed opens SECURITY.md or the README, not the
    code of conduct, and the moment they are most likely to be asked where
    they are is while a maintainer is debugging their network.
    """
    conduct = read("CODE_OF_CONDUCT.md")
    assert "name their country" in conduct or "which country" in conduct.lower(), (
        "the code of conduct no longer carries the rule about not asking "
        "where someone is")
    assert "network" in conduct, (
        "the rule should cover network conditions, not only location")

    security = read("SECURITY.md")
    assert "without identifying yourself" in security.lower() or \
        "where you are" in security.lower(), (
        "SECURITY.md does not tell a reporter they need not identify "
        "themselves, which is where they will look first")
