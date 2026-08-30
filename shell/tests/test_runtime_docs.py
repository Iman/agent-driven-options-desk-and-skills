"""The generated runtime files must stay derived from the skills.

They also have to stay derived from the CLI. Codex and Gemini CLI get no
skills at all, so AGENTS.md and GEMINI.md are their entire instruction
surface, and for a while three shipped commands (expiries, keys and
dashboard) had no skill and so appeared in neither file. A user of those
runtimes could not find out they existed.

The fix was to generate the command list from the parser instead of
writing it down, and these tests are what stops it regressing: they ask
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
            assert "## Skill: options-greeks" in on_disk
            assert "not investment advice" in on_disk


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
