"""The installer is the first thing a new user runs, so a syntax error or a
changed flag in it is a first-impression failure. These tests exercise the
paths that do not touch the machine."""

import shutil
import os
import subprocess
import sys
from pathlib import Path

import pytest

INSTALLER = Path(__file__).resolve().parent.parent.parent / "install.sh"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None,
                                reason="bash not available")


def _run(*args, **kwargs):
    return subprocess.run(["bash", str(INSTALLER), *args],
                          capture_output=True, text=True, **kwargs)


def test_installer_is_syntactically_valid():
    result = subprocess.run(["bash", "-n", str(INSTALLER)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_help_lists_the_safety_flags():
    result = _run("--help")
    assert result.returncode == 0
    for flag in ("--dry-run", "--uninstall", "--no-engine", "--no-mcp",
                 "--prefix"):
        assert flag in result.stdout


def test_dry_run_changes_nothing(tmp_path):
    prefix = tmp_path / "opt"
    result = _run("--dry-run", "--prefix", str(prefix),
                  "--bin-dir", str(tmp_path / "bin"),
                  "--skills-dir", str(tmp_path / "skills"), "--no-mcp")
    assert result.returncode == 0, result.stderr
    assert "would run" in result.stdout
    # Nothing may exist afterwards. A dry run that creates directories is
    # not a dry run.
    assert not prefix.exists()
    assert not (tmp_path / "bin").exists()
    assert not (tmp_path / "skills").exists()


def test_dry_run_states_the_engine_licence():
    result = _run("--dry-run", "--no-mcp")
    assert "AGPL-3.0" in result.stdout
    assert "network service" in result.stdout


def test_no_engine_skips_the_agpl_component(tmp_path):
    result = _run("--dry-run", "--no-engine", "--no-mcp",
                  "--prefix", str(tmp_path / "opt"))
    assert "Skipping the analytics engine" in result.stdout
    assert "/engine" not in result.stdout.split("Skipping")[1]


def test_unknown_flag_fails_loudly():
    result = _run("--not-a-flag")
    assert result.returncode != 0
    assert "unknown option" in result.stderr


def test_clone_mode_names_the_repository_it_could_not_reach(tmp_path):
    """A failed clone has to say which repository it tried.

    This test has now been wrong twice, in opposite directions, and both
    times because it depended on the state of the world. It first asserted
    the installer refuses and asks for --repo, which held only while REPO
    had no default. It then asserted the clone fails, which held only while
    the repository did not exist on GitHub; publishing it made the piped
    install succeed and the assertion false.

    So it no longer touches the network or the real repository. It points
    at an absolute path that does not exist, which the guard allows and
    git cannot clone, and asserts the failure names what it tried. An error
    reading only "clone failed" leaves the reader guessing.
    """
    missing = tmp_path / "no-such-checkout"
    piped = tmp_path / "piped.sh"
    piped.write_text(INSTALLER.read_text(encoding="utf-8"), encoding="utf-8")
    result = subprocess.run(
        ["bash", "-c", "cat {} | bash -s -- --repo {} --prefix {} "
                       "--no-mcp".format(piped, missing, tmp_path / "opt")],
        capture_output=True, text=True,
        env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
    assert result.returncode != 0
    output = result.stderr + result.stdout
    assert str(missing) in output, output[-400:]


def test_the_repo_default_matches_the_documented_install_line(tmp_path):
    """The one-line install and the script must name the same repository.

    They are written in two places, a shell default and a markdown code
    fence, and a mismatch produces an install command that 404s while the
    script works, or the reverse.
    """
    import re

    script = INSTALLER.read_text(encoding="utf-8")
    default = re.search(r'REPO="\$\{OPTIONDESK_REPO:-([^}"]*)\}"', script)
    assert default, "the installer no longer carries a repository default"
    named = default.group(1)
    if not named:
        return

    readme = (INSTALLER.parent / "README.md").read_text(encoding="utf-8")
    if "raw.githubusercontent.com" in readme:
        assert named in readme, (
            "install.sh defaults to {} and the README documents a different "
            "repository".format(named))


# ------------------------------------------------- supply chain: the repo

def test_a_bare_owner_name_is_refused_rather_than_resolved_locally(tmp_path):
    """`git clone owner/name` clones ./owner/name when it exists.

    WHAT WOULD BREAK. The installer's REPO default was set to the bare
    identifier `Iman/agent-driven-options-desk-and-skills`. Git resolves
    that against the current working directory, so the one-line install
    never reached GitHub at all, and anyone running it from a directory
    where that path could be planted would have installed whatever was
    sitting there. Reproduced by planting the directory and watching the
    clone take it.

    A local checkout is still installable. It just has to be said out loud,
    as an absolute path or a file:// URL, rather than arriving disguised as
    a GitHub identifier.
    """
    planted = tmp_path / "Iman" / "agent-driven-options-desk-and-skills"
    (planted / "shell").mkdir(parents=True)
    (planted / "shell" / "pyproject.toml").write_text(
        '[project]\nname = "planted"\n', encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(planted)], check=True)
    subprocess.run(["git", "-C", str(planted), "add", "-A"], check=True)
    # commit.gpgsign is on globally for this user, and a throwaway fixture
    # commit has nobody to type a passphrase: without this the test hangs
    # until gpg times out and then fails on "failed to write commit
    # object". A test must not depend on the developer's signing setup.
    subprocess.run(
        ["git", "-C", str(planted), "-c", "user.email=t@t", "-c",
         "user.name=t", "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false",
         "commit", "-qm", "planted"], check=True)

    piped = tmp_path / "piped.sh"
    piped.write_text(INSTALLER.read_text(encoding="utf-8"), encoding="utf-8")
    result = subprocess.run(
        ["bash", "-c",
         "cd {} && cat {} | bash -s -- --repo Iman/"
         "agent-driven-options-desk-and-skills --prefix {} --no-mcp".format(
             tmp_path, piped, tmp_path / "opt")],
        capture_output=True, text=True,
        env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))

    assert result.returncode != 0, (
        "the installer accepted a bare owner/name and would have cloned the "
        "planted directory")
    assert "not an explicit remote" in result.stderr, result.stderr
    assert not (tmp_path / "opt").exists(), (
        "the planted source reached the install prefix")


def test_the_repo_default_is_a_full_url():
    """The default is what almost everyone runs, so it carries the risk."""
    import re

    script = INSTALLER.read_text(encoding="utf-8")
    default = re.search(r'REPO="\$\{OPTIONDESK_REPO:-([^}"]*)\}"', script)
    assert default, "the installer no longer carries a repository default"
    value = default.group(1)
    assert value.startswith(("https://", "ssh://", "git@")), (
        "the default {!r} is not an explicit remote, so git would resolve it "
        "against the working directory".format(value))


def test_an_absolute_local_path_is_still_allowed(tmp_path):
    """Refusing the ambiguous case must not refuse the deliberate one."""
    result = subprocess.run(
        ["bash", "-c",
         "cat {} | bash -s -- --repo {} --ref main --prefix {} --no-mcp "
         "--dry-run".format(
             INSTALLER, tmp_path / "somewhere", tmp_path / "opt")],
        capture_output=True, text=True)
    assert "not an explicit remote" not in result.stderr, result.stderr


# --------------------------------------------- two skill destinations
#
# Claude Code reads ~/.claude/skills. Codex and ChatGPT read the shared
# ~/.agents/skills convention. Installing into one and not the other leaves
# half the agent runtimes on the machine unable to see the skills, with
# nothing in the output to say why.
#
# These tests run the installer for real, not as a dry run, so every one of
# them redirects HOME. Every default destination is derived from it, and a
# test that forgot one would write into the home directory of whoever runs
# the suite.

SKILLS_SOURCE = INSTALLER.parent / "shell" / "skills"
MARKER = ".installed-by-optiondesk"


def _source_skill_names():
    """The skills the installer would pick, chosen by its own rule.

    Hardcoding today's five would keep passing while a sixth went
    uninstalled.
    """
    return sorted(p.name for p in SKILLS_SOURCE.iterdir()
                  if (p / "SKILL.md").is_file())


def _run_isolated(tmp_path, *args, **env):
    """Run the installer with HOME redirected inside tmp_path."""
    return subprocess.run(
        ["bash", str(INSTALLER), *args],
        capture_output=True, text=True,
        env=dict(os.environ, HOME=str(tmp_path), **env))


def _install_skills(tmp_path, claude, agents, *extra):
    """--skills-only keeps this to the copy: no venv, no pip, no network."""
    return _run_isolated(tmp_path, "--skills-only",
                         "--skills-dir", str(claude), *extra,
                         OPTIONDESK_AGENTS_SKILLS_DIR=str(agents))


def _uninstall(tmp_path, claude, agents):
    """--no-mcp is not optional here.

    Without it the uninstall path shells out to whichever of claude, codex
    and gemini exist on the machine and removes the MCP entry from the real
    user config of whoever runs the suite.
    """
    return _run_isolated(tmp_path, "--uninstall", "--no-mcp",
                         "--skills-dir", str(claude),
                         "--prefix", str(tmp_path / "opt"),
                         "--bin-dir", str(tmp_path / "bin"),
                         OPTIONDESK_AGENTS_SKILLS_DIR=str(agents))


def _tree(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*")) \
        if root.exists() else []


def test_the_skills_reach_both_destinations(tmp_path):
    claude = tmp_path / "claude-skills"
    agents = tmp_path / "agents-skills"
    result = _install_skills(tmp_path, claude, agents)
    assert result.returncode == 0, result.stderr

    names = _source_skill_names()
    assert names, "the checkout holds no skills to install"
    for destination in (claude, agents):
        missing = [name for name in names
                   if not (destination / name / "SKILL.md").is_file()]
        assert not missing, "{} did not receive {}".format(destination,
                                                           missing)


def test_both_destinations_carry_the_marker(tmp_path):
    """The marker is the only thing that authorises removal later.

    A copy installed without it is never cleaned up by --uninstall, and a
    re-run reads it as somebody else's directory and refuses to touch it.
    """
    claude = tmp_path / "claude-skills"
    agents = tmp_path / "agents-skills"
    result = _install_skills(tmp_path, claude, agents)
    assert result.returncode == 0, result.stderr

    for destination in (claude, agents):
        unmarked = [name for name in _source_skill_names()
                    if not (destination / name / MARKER).is_file()]
        assert not unmarked, "{} in {} carry no marker".format(unmarked,
                                                               destination)


def test_both_destinations_get_the_disclaimer_the_skills_point_at(tmp_path):
    """Every SKILL.md ends by pointing at DISCLAIMER.md.

    It says the file "ships beside this skill when it is installed from a
    package and sits at the repository root otherwise". An install from
    this script is neither: the skill lands in a skills directory with no
    repository around it, so the pointer resolved to nothing. The zips and
    the plugin bundle already carry the file; this is the same fix for the
    path the installer owns.
    """
    claude = tmp_path / "claude-skills"
    agents = tmp_path / "agents-skills"
    result = _install_skills(tmp_path, claude, agents)
    assert result.returncode == 0, result.stderr

    expected = (INSTALLER.parent / "DISCLAIMER.md").read_bytes()
    for destination in (claude, agents):
        for name in _source_skill_names():
            carried = destination / name / "DISCLAIMER.md"
            assert carried.is_file(), "{} points at a file that is not there"\
                .format(carried)
            assert carried.read_bytes() == expected, (
                "{} is not the disclaimer at the repository root".format(
                    carried))


def test_a_missing_disclaimer_warns_and_installs_anyway(tmp_path):
    """Carrying the disclaimer must not become a new way to fail.

    The substance of it is inline in every SKILL.md already, so a checkout
    without the file at its root is worth a warning and nothing more. This
    builds a checkout with no DISCLAIMER.md rather than deleting the real
    one.
    """
    checkout = tmp_path / "checkout"
    (checkout / "shell" / "skills" / "options-greeks").mkdir(parents=True)
    shutil.copy(INSTALLER, checkout / "install.sh")
    shutil.copy(SKILLS_SOURCE.parent / "pyproject.toml",
                checkout / "shell" / "pyproject.toml")
    shutil.copy(SKILLS_SOURCE / "options-greeks" / "SKILL.md",
                checkout / "shell" / "skills" / "options-greeks" / "SKILL.md")
    assert not (checkout / "DISCLAIMER.md").exists()

    home = tmp_path / "home"
    home.mkdir()
    result = subprocess.run(
        ["bash", str(checkout / "install.sh"), "--skills-only"],
        capture_output=True, text=True,
        env=dict(os.environ, HOME=str(home)))
    assert result.returncode == 0, result.stderr
    assert "no DISCLAIMER.md" in result.stderr, (
        "the installer said nothing about the file the skills point at")
    for destination in (home / ".claude" / "skills",
                        home / ".agents" / "skills"):
        assert (destination / "options-greeks" / "SKILL.md").is_file(), (
            "a missing disclaimer stopped the skill reaching {}".format(
                destination))
        assert not (destination / "options-greeks" / "DISCLAIMER.md").exists()


def test_dry_run_creates_neither_destination(tmp_path):
    """A dry run that creates a directory is not a dry run.

    It also has to say where it would write, in the conditional. An earlier
    version of the MCP step printed the past tense while changing nothing.
    """
    claude = tmp_path / "claude-skills"
    agents = tmp_path / "agents-skills"
    result = _install_skills(tmp_path, claude, agents, "--dry-run")
    assert result.returncode == 0, result.stderr

    assert not claude.exists()
    assert not agents.exists()
    assert not (tmp_path / ".agents").exists()

    conditional = [line for line in result.stdout.splitlines()
                   if "would install" in line]
    for destination in (claude, agents):
        assert any(str(destination) in line for line in conditional), (
            "the dry run never says it would write to {}".format(destination))
    assert "  installed skill" not in result.stdout, (
        "the dry run claimed an install in the past tense")


def test_the_default_codex_destination_is_dot_agents_under_home(tmp_path):
    """Codex reads $HOME/.agents/skills, so that is where the default goes.

    Asserted against a redirected HOME rather than a flag, because the
    default is what almost everybody gets.
    """
    claude = tmp_path / "claude-skills"
    result = _run_isolated(tmp_path, "--skills-only",
                           "--skills-dir", str(claude))
    assert result.returncode == 0, result.stderr

    default = tmp_path / ".agents" / "skills"
    missing = [name for name in _source_skill_names()
               if not (default / name / "SKILL.md").is_file()]
    assert not missing, "{} did not receive {}".format(default, missing)


def test_the_agents_skills_dir_flag_moves_the_codex_destination(tmp_path):
    chosen = tmp_path / "elsewhere"
    result = _run_isolated(tmp_path, "--skills-only",
                           "--skills-dir", str(tmp_path / "claude-skills"),
                           "--agents-skills-dir", str(chosen))
    assert result.returncode == 0, result.stderr

    missing = [name for name in _source_skill_names()
               if not (chosen / name / "SKILL.md").is_file()]
    assert not missing, "{} did not receive {}".format(chosen, missing)
    assert not (tmp_path / ".agents").exists(), (
        "the flag was accepted and the default was written to anyway")


def test_help_lists_the_codex_skills_flag():
    result = _run("--help")
    assert result.returncode == 0
    assert "--agents-skills-dir" in result.stdout
    assert "OPTIONDESK_AGENTS_SKILLS_DIR" in result.stdout


def test_installing_twice_is_idempotent(tmp_path):
    """The second run must not read its own copy as somebody else's."""
    claude = tmp_path / "claude-skills"
    agents = tmp_path / "agents-skills"
    first = _install_skills(tmp_path, claude, agents)
    assert first.returncode == 0, first.stderr

    before = {str(d): _tree(d) for d in (claude, agents)}
    for destination, listing in before.items():
        assert listing, "nothing was installed into {} on the first run"\
            .format(destination)

    second = _install_skills(tmp_path, claude, agents)
    assert second.returncode == 0, second.stderr
    assert "leaving it alone" not in second.stderr, (
        "the second run refused to touch what the first run wrote")
    assert {str(d): _tree(d) for d in (claude, agents)} == before


def test_uninstall_removes_the_skills_from_both_destinations(tmp_path):
    claude = tmp_path / "claude-skills"
    agents = tmp_path / "agents-skills"
    installed = _install_skills(tmp_path, claude, agents)
    assert installed.returncode == 0, installed.stderr

    names = _source_skill_names()
    for destination in (claude, agents):
        assert (destination / names[0]).is_dir(), (
            "nothing was installed into {}, so this proves nothing about "
            "uninstall".format(destination))

    result = _uninstall(tmp_path, claude, agents)
    assert result.returncode == 0, result.stderr

    for destination in (claude, agents):
        left = [name for name in names if (destination / name).exists()]
        assert not left, "{} still holds {}".format(destination, left)
        # The disclaimer is copied in beside SKILL.md, so it goes with the
        # directory rather than being left behind as an orphan.
        assert not (destination / names[0] / "DISCLAIMER.md").exists()


def test_uninstall_leaves_a_directory_it_did_not_install(tmp_path):
    """A same-named skill directory somebody else wrote is not ours to
    delete, in either destination.

    Only the marker authorises removal. The marked directory in the same
    run has to go, or a script that removes nothing at all would pass this
    test.
    """
    claude = tmp_path / "claude-skills"
    agents = tmp_path / "agents-skills"
    for destination in (claude, agents):
        ours = destination / "options-greeks"
        ours.mkdir(parents=True)
        (ours / "SKILL.md").write_text("ours\n", encoding="utf-8")
        (ours / MARKER).write_text("", encoding="utf-8")
        theirs = destination / "options-strategy"
        theirs.mkdir(parents=True)
        (theirs / "SKILL.md").write_text("hand written\n", encoding="utf-8")

    result = _uninstall(tmp_path, claude, agents)
    assert result.returncode == 0, result.stderr

    for destination in (claude, agents):
        assert not (destination / "options-greeks").exists(), (
            "the marked directory survived uninstall in {}".format(
                destination))
        kept = destination / "options-strategy" / "SKILL.md"
        assert kept.is_file(), (
            "uninstall deleted an unmarked directory in {}".format(
                destination))
        assert kept.read_text(encoding="utf-8") == "hand written\n"
