"""The generated runtime files must stay derived from the skills.

WHY THE PREMISE CHANGED. This file used to open by asserting that "Codex
and Gemini CLI get no skills at all", and the generator acted on it by
copying all five SKILL.md bodies into both AGENTS.md and GEMINI.md. That
was false for Codex. OpenAI documents Codex discovering skills from
$CWD/.agents/skills, its parents up to $REPO_ROOT/.agents/skills, and
$HOME/.agents/skills, and it loads them progressively: name and
description first, the full body only once a skill is selected. This
repository has .agents/skills symlinked to shell/skills, so Codex already
had the five natively. Repeating them in AGENTS.md added roughly 24 KB of
duplication and defeated the progressive disclosure that is the point of
the skill format.

So AGENTS.md now points at .agents/skills instead of inlining it, and the
tests below pin that: no skill body in AGENTS.md, the directory named, and
the pointer aimed at a path that really does hold the same five skills.

GEMINI.md keeps the full compiled bodies. No equivalent discovery path for
Gemini CLI has been verified, and dropping the bodies on an unverified
guess would silently remove that runtime's only instruction surface.

The files also have to stay derived from the CLI. For a while three
shipped commands (expiries, keys and dashboard) had no skill and so
appeared in neither file. A user of those runtimes could not find out they
existed. The fix was to generate the command list from the parser instead
of writing it down, and these tests are what stops it regressing: they ask
the real parser for its subcommands and require every one of them in both
copies of both files. A command added without regenerating fails here.
"""

import re
import pytest
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

RUNTIME_FILES = ("AGENTS.md", "GEMINI.md")


def _generator():
    sys.path.insert(0, str(ROOT / "tools"))
    import gen_runtime_docs

    return gen_runtime_docs


def _parser():
    """The parser the shipped CLI builds, loaded the way the generator does."""
    parser, reason = _generator().load_parser()
    assert parser is not None, reason
    return parser


def _reference(target):
    """The command reference section of one generated file."""
    text = target.read_text(encoding="utf-8")
    assert "## Command reference" in text, (
        "{} has no command reference section. Run python "
        "tools/gen_runtime_docs.py".format(target))
    return text.split("## Command reference", 1)[1]


def _body_fingerprints():
    """One line from each skill body that would not appear by coincidence.

    Used to tell "the body is in this file" from "the skill is mentioned in
    this file". A name or a heading proves neither, because the lean
    AGENTS.md names all five on purpose; a forty-character sentence out of
    the body proves the body itself was copied in.
    """
    generator = _generator()
    prints = {}
    for path in sorted((ROOT / "skills").glob("*/SKILL.md")):
        _fields, body = generator.parse_skill(path)
        longest = max(body.splitlines(), key=len)
        assert len(longest) > 40, (
            "{} has no line long enough to fingerprint".format(path))
        prints[path.parent.name] = longest
    assert prints, "no skills found"
    return prints


def test_runtime_files_are_in_sync_with_the_skills():
    """Compare generated text against what is on disk.

    The earlier version ran the generator as a subprocess with cwd set to
    the repository, then asserted substrings against the file it had just
    overwritten. Every assertion was a tautology, the test repaired any
    drift it was meant to detect, and running pytest modified the working
    tree. Proven by replacing both files with garbage: the test passed and
    the garbage was silently repaired.
    """
    generator = _generator()
    for name in ("AGENTS.md", "GEMINI.md"):
        for target in generator.targets(name):
            expected = generator.generate(name, root=target.parent)
            on_disk = target.read_text(encoding="utf-8")
            assert on_disk == expected, (
                "{} is stale. Run python tools/gen_runtime_docs.py".format(
                    target))
            # Both files still carry the standing rules and name every
            # skill. The compiled bodies are GEMINI.md only now, so the
            # assertion that used to require "## Skill: options-greeks" in
            # both encoded the old premise that Codex could not load a
            # skill; the two tests below check each file separately.
            #
            # The disclaimer assertion moved with it. It used to read
            # "not investment advice", which is wording from the skill
            # bodies rather than from FOOTER, so on the lean AGENTS.md it
            # failed. FOOTER says "Nothing here is investment advice ...
            # See DISCLAIMER.md", and that is what both files really
            # guarantee.
            assert "investment advice" in on_disk
            assert "DISCLAIMER.md" in on_disk
            assert "options-greeks" in on_disk


def test_the_header_paths_resolve_from_the_file_that_carries_them():
    """A path in a generated file is read relative to that file.

    The header names the generator and the skills directory. Both live one
    level down from the repository root and at the top of the shell
    package, so one hardcoded string is correct in one copy and wrong in
    the other. It was wrong at the root: neither tools/ nor skills/ exists
    there, and a reader following the pointer found nothing.
    """
    generator = _generator()
    for name in ("AGENTS.md", "GEMINI.md"):
        for target in generator.targets(name):
            text = target.read_text(encoding="utf-8")
            header = text.split("\n")[2]
            for fragment in header.split():
                if fragment.endswith("gen_runtime_docs.py"):
                    assert (target.parent / fragment).exists(), (
                        "{} points at {}, which does not exist beside "
                        "it".format(target, fragment))
                if fragment.startswith(("skills/", "shell/skills/")):
                    assert (target.parent / fragment.rstrip(".")).exists(), (
                        "{} points at {}, which does not exist beside "
                        "it".format(target, fragment))


def test_the_runtime_files_exist_where_a_runtime_looks_for_them():
    """A copy only inside the shell package is one nobody loads.

    Codex and Gemini CLI read their instruction file from the working
    directory and upward. Someone who opens this repository at its root,
    which is the normal thing to do, gets nothing if the only copy is in
    shell/. This is the check that the root copy did not quietly stop being
    written.
    """
    for name in ("AGENTS.md", "GEMINI.md"):
        assert (ROOT.parent / name).exists(), (
            "{} is missing from the repository root".format(name))
        assert (ROOT / name).exists(), (
            "{} is missing from the shell package".format(name))


def test_generator_writes_both_files_when_run(tmp_path):
    # The generator itself is exercised in a copy, never in the repository.
    import shutil

    sandbox = tmp_path / "shell"
    shutil.copytree(ROOT, sandbox, ignore=shutil.ignore_patterns(
        ".venv", "__pycache__", ".pytest_cache", "*.egg-info"))
    result = subprocess.run(
        [sys.executable, str(sandbox / "tools" / "gen_runtime_docs.py")],
        capture_output=True, text=True, cwd=str(sandbox))
    assert result.returncode == 0, result.stderr
    for name in ("AGENTS.md", "GEMINI.md"):
        assert (sandbox / name).read_text(encoding="utf-8").startswith("#")
        # The parent copy, which is the one a runtime opened at the
        # repository root will actually read.
        assert (sandbox.parent / name).read_text(
            encoding="utf-8").startswith("#")


def test_every_skill_has_valid_frontmatter():
    sys.path.insert(0, str(ROOT / "tools"))
    import gen_runtime_docs

    skills = sorted((ROOT / "skills").glob("*/SKILL.md"))
    assert skills, "no skills found"
    for path in skills:
        fields, body = gen_runtime_docs.parse_skill(path)
        assert fields["name"] == path.parent.name
        # The description is what a runtime matches on, so it must say both
        # what the skill does and when to reach for it.
        assert len(fields["description"]) > 80
        assert "Use when" in fields["description"]
        assert body


def test_every_shipped_command_is_documented_in_both_copies():
    """Ask the parser what exists, then require it in all four files.

    This is the check that would have caught the gap. `expiries`, `keys`
    and `dashboard` ship, have no skill, and were in neither file; nothing
    failed, because nothing compared the two lists. The names come from
    build_parser() rather than from a list kept here, so a thirteenth
    command is covered the day it is added.
    """
    generator = _generator()
    expected = [name for name, _help, _sub in generator.subcommands(_parser())]
    assert len(expected) > 1, "the parser exposed no subcommands"
    for name in ("expiries", "keys", "dashboard"):
        assert name in expected, "{} is no longer a command".format(name)
    for filename in RUNTIME_FILES:
        for target in generator.targets(filename):
            section = _reference(target)
            for name in expected:
                found = re.search(
                    r"^- `optiondesk {}[ `]".format(re.escape(name)),
                    section, re.M)
                assert found, (
                    "{} documents no `{}` command. Run python "
                    "tools/gen_runtime_docs.py".format(target, name))


def test_every_flag_of_every_command_is_listed():
    """A flag added to a command is a flag no runtime can discover.

    Same failure as a missing command, one level down, and the same fix:
    the names are read from the parser, so this cannot be satisfied by
    editing the generated file.
    """
    generator = _generator()
    for filename in RUNTIME_FILES:
        for target in generator.targets(filename):
            section = _reference(target)
            for name, _help, sub in generator.subcommands(_parser()):
                for flag in generator.flag_names(sub):
                    assert flag in section, (
                        "{} does not list {} of `optiondesk {}`. Run python "
                        "tools/gen_runtime_docs.py".format(target, flag, name))


def test_the_command_reference_points_at_the_cli_beside_it():
    """The path in the section is read relative to the file that carries it.

    The same trap as the header. From the repository root the CLI is at
    shell/src/optiondesk/cli/ and from inside the shell package it is at
    src/optiondesk/cli/, so one hardcoded string would be wrong in one of
    the two copies.
    """
    generator = _generator()
    for filename in RUNTIME_FILES:
        for target in generator.targets(filename):
            section = _reference(target)
            named = set(re.findall(r"\b((?:shell/)?src/optiondesk/cli/)",
                                   section))
            assert named, "{} names no CLI source directory".format(target)
            for fragment in named:
                assert (target.parent / fragment).is_dir(), (
                    "{} points at {}, which does not exist beside it".format(
                        target, fragment))


def test_an_unimportable_shell_is_reported_and_writes_nothing():
    """The generator now needs the package. It must not crash without it.

    Before this section existed the generator read only files, so it ran
    anywhere. Now it imports the CLI, and someone who has only checked the
    repository out has to get a sentence rather than a traceback. Writing
    the files anyway would be worse than refusing: the result would look
    complete while silently missing every command.
    """
    generator = _generator()
    before = {}
    for filename in RUNTIME_FILES:
        for target in generator.targets(filename):
            before[target] = target.read_bytes()

    original = generator.CLI_MODULE
    generator.CLI_MODULE = "optiondesk.no_such_cli_module"
    try:
        parser, reason = generator.load_parser()
        assert parser is None
        assert "optiondesk.no_such_cli_module" in reason
        try:
            generator.generate("AGENTS.md")
        except SystemExit as exc:
            assert "AGENTS.md" in str(exc) and reason in str(exc)
        else:
            raise AssertionError("generate() did not refuse")
        assert generator.main() == 1
    finally:
        generator.CLI_MODULE = original

    for target, content in before.items():
        assert target.read_bytes() == content, (
            "{} was rewritten during a failed run".format(target))


def test_every_skill_frontmatter_is_valid_yaml():
    """Our own parser is a line splitter. Everyone else uses YAML.

    WHAT WOULD BREAK. options-strategy described itself as building
    structures "from a chain: iron condors, ...". That colon ends the
    scalar for a real YAML parser, so the whole frontmatter failed to load
    and the skill was silently skipped by anything that reads it properly.
    Measured against the live repository: `npx skills add` listed four of
    our five skills, and nothing here noticed, because
    test_every_skill_has_valid_frontmatter uses the same forgiving splitter
    the generator does.
    """
    yaml = pytest.importorskip(
        "yaml", reason="pyyaml is needed to check the frontmatter the way "
                       "third-party tools read it")

    for path in sorted((ROOT / "skills").glob("*/SKILL.md")):
        text = path.read_text(encoding="utf-8")
        assert text.startswith("---"), path
        frontmatter = text.split("---", 2)[1]
        try:
            fields = yaml.safe_load(frontmatter)
        except yaml.YAMLError as exc:
            raise AssertionError(
                "{} has frontmatter that is not valid YAML, so tools that "
                "parse it properly will skip this skill: {}".format(
                    path.parent.name, str(exc).splitlines()[0]))
        assert isinstance(fields, dict), path
        assert fields.get("name") == path.parent.name, path
        assert fields.get("description"), path


def test_the_generator_and_a_yaml_parser_agree():
    """The quotes are syntax, not content, and must not reach the output."""
    yaml = pytest.importorskip("yaml")
    generator = _generator()

    for path in sorted((ROOT / "skills").glob("*/SKILL.md")):
        text = path.read_text(encoding="utf-8")
        strict = yaml.safe_load(text.split("---", 2)[1])
        ours, _ = generator.parse_skill(path)
        assert ours["description"] == strict["description"], (
            "{}: the generator and a YAML parser disagree about the "
            "description".format(path.parent.name))


def test_agents_md_does_not_embed_the_skill_bodies():
    """Codex loads the skills itself, so copying them in is dead weight.

    THE PREMISE THAT CHANGED. The generator inlined all five SKILL.md
    bodies into AGENTS.md because it assumed Codex could not load a skill.
    OpenAI documents the opposite: Codex scans .agents/skills from the
    working directory up to the repository root, and reads a body only once
    the skill is selected. Inlining all five cost roughly 24 KB and forced
    every body into context whether or not it was relevant, which is the
    exact cost progressive disclosure exists to avoid.

    This checks the bodies are gone, not merely shortened.
    """
    generator = _generator()
    prints = _body_fingerprints()
    for target in generator.targets("AGENTS.md"):
        text = target.read_text(encoding="utf-8")
        assert "## Skill:" not in text, (
            "{} still compiles skill bodies in. Codex reads them from "
            ".agents/skills already".format(target))
        for name, fingerprint in prints.items():
            assert fingerprint not in text, (
                "{} still contains the body of {}: {!r}".format(
                    target, name, fingerprint[:60]))


def test_agents_md_names_where_codex_finds_the_skills():
    """A file that drops the bodies must say where they went.

    Otherwise the reader is worse off than before: no skills in the file
    and no pointer either. The path has to be the one Codex actually scans,
    and it has to hold the same five skills the generator read.
    """
    generator = _generator()
    prints = _body_fingerprints()
    for target in generator.targets("AGENTS.md"):
        text = target.read_text(encoding="utf-8")
        assert ".agents/skills" in text, (
            "{} does not tell Codex that the skills live in "
            ".agents/skills".format(target))
        for name in prints:
            assert name in text, (
                "{} does not name the {} skill".format(target, name))

    # The pointer must not aim at nothing. ROOT is the shell package, so
    # the repository root, where Codex resolves $REPO_ROOT/.agents/skills,
    # is its parent.
    discovered = {path.parent.name
                  for path in (ROOT.parent / ".agents" / "skills").glob(
                      "*/SKILL.md")}
    assert discovered == set(prints), (
        ".agents/skills reaches {} but the generator compiled from "
        "{}".format(sorted(discovered), sorted(prints)))


def test_gemini_md_still_embeds_every_skill_body():
    """Gemini CLI keeps the compiled copy until a discovery path is proven.

    No equivalent of .agents/skills has been verified for Gemini CLI, so
    GEMINI.md remains that runtime's entire instruction surface. Dropping
    the bodies from it on the strength of the Codex finding would remove
    the only thing Gemini has, which is why the two files are asserted
    separately rather than together.
    """
    generator = _generator()
    prints = _body_fingerprints()
    for target in generator.targets("GEMINI.md"):
        text = target.read_text(encoding="utf-8")
        for name, fingerprint in prints.items():
            assert "## Skill: {}".format(name) in text, (
                "{} lost the {} section. Run python "
                "tools/gen_runtime_docs.py".format(target, name))
            assert fingerprint in text, (
                "{} names {} but does not carry its body".format(target,
                                                                 name))
