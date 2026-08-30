"""The installer is the first thing a new user runs, so a syntax error or a
changed flag in it is a first-impression failure. These tests exercise the
paths that do not touch the machine."""

import shutil
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


def test_clone_mode_requires_a_repo_url(tmp_path):
    # Simulate the curl path: the script cannot see its own directory, so it
    # must ask for a repository rather than guessing one.
    piped = tmp_path / "piped.sh"
    piped.write_text(INSTALLER.read_text(encoding="utf-8"), encoding="utf-8")
    result = subprocess.run(
        ["bash", "-c", "cat {} | bash -s -- --prefix {} --no-mcp".format(
            piped, tmp_path / "opt")],
        capture_output=True, text=True)
    assert result.returncode != 0
    assert "--repo" in result.stderr
