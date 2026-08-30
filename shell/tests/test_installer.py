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
    """The curl path cannot see its own directory, so it clones.

    This used to assert that the script refused and asked for --repo,
    because REPO had no default. It has one now, so the honest contract is
    different: it attempts the default and, when that cannot be reached,
    the failure has to name what it tried. An error that says only "clone
    failed" leaves the reader guessing which repository was even involved.
    """
    piped = tmp_path / "piped.sh"
    piped.write_text(INSTALLER.read_text(encoding="utf-8"), encoding="utf-8")
    result = subprocess.run(
        ["bash", "-c", "cat {} | bash -s -- --prefix {} --no-mcp".format(
            piped, tmp_path / "opt")],
        capture_output=True, text=True,
        env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
    assert result.returncode != 0
    output = result.stderr + result.stdout
    assert "agent-driven-options-desk-and-skills" in output, output[-400:]


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
