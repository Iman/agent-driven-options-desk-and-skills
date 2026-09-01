"""The container must not quietly throw away the artifacts it produces.

Artifacts are the product here. A container run without a volume writes
them inside itself and loses them on exit, having printed a summary that
reads exactly like a successful run. This project has spent a lot of effort
removing failures that look like successes, so shipping a new one in an
entrypoint would be perverse.

The first version of this image did exactly that, and not through the
entrypoint's logic. The Dockerfile declared VOLUME ["/artifacts"], which
makes Docker create an ANONYMOUS volume and mount it at run time, so the
entrypoint's check for a real mount was always satisfied. With --rm that
anonymous volume is discarded, so the data was lost anyway and the guard
could never see it. Measured, not reasoned about: mountpoint reported
/artifacts as a mount and the chain snapshot vanished.

These tests run the entrypoint itself, on this machine, with a stub on PATH
in place of the real command.
"""

import os
import pathlib
import stat
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
ENTRYPOINT = ROOT / "docker-entrypoint.sh"
DOCKERFILE = ROOT / "Dockerfile"

pytestmark = pytest.mark.skipif(not ENTRYPOINT.exists(),
                                reason="no container in this checkout")


def _run(tmp_path, argv, env=None):
    """Run the entrypoint with a stub optiondesk on PATH."""
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir(exist_ok=True)
    stub = stub_dir / "optiondesk"
    stub.write_text("#!/bin/sh\necho \"ran: $*\"\n", encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)

    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(exist_ok=True)

    environment = dict(os.environ)
    environment["PATH"] = "{}:{}".format(stub_dir, environment["PATH"])
    environment["OPTIONDESK_ARTIFACTS"] = str(artifacts)
    environment.update(env or {})
    return subprocess.run(["sh", str(ENTRYPOINT)] + argv, env=environment,
                          capture_output=True, text=True)


def test_a_writing_command_without_a_mount_is_refused(tmp_path):
    """The whole point. Exit 64 rather than a run whose output evaporates."""
    result = _run(tmp_path, ["chain", "SPY"])
    assert result.returncode == 64, result.stdout + result.stderr
    assert "No volume is mounted" in result.stderr
    assert "ran:" not in result.stdout, "the command ran anyway"


def test_the_commands_that_write_nothing_still_work(tmp_path):
    """doctor and keys are how somebody checks an install, and a bare
    docker run has to be able to reach them.
    """
    for argv in (["doctor"], ["keys", "list"], ["--help"]):
        result = _run(tmp_path, argv)
        assert result.returncode == 0, argv
        assert "ran:" in result.stdout


def test_the_escape_hatch_warns_rather_than_refusing(tmp_path):
    """A throwaway run is legitimate. It must say what it is doing."""
    result = _run(tmp_path, ["chain", "SPY"],
                  env={"OPTIONDESK_ALLOW_EPHEMERAL": "1"})
    assert result.returncode == 0
    assert "discarded" in result.stderr
    assert "ran: chain SPY" in result.stdout


def test_an_artifact_directory_with_files_is_accepted(tmp_path):
    """A directory that already holds artifacts is a mount in every case
    that matters, and mountpoint is not available on every host running
    this check.
    """
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(exist_ok=True)
    (artifacts / "chain_SPY_2026-09-18.json").write_text("{}",
                                                         encoding="utf-8")
    result = _run(tmp_path, ["greeks"])
    assert result.returncode == 0
    assert "ran: greeks" in result.stdout


def test_the_dockerfile_declares_no_volume():
    """VOLUME defeats the check above by creating an anonymous mount, and
    then --rm deletes it. This is the test for the defect that was found by
    building the image and losing a chain snapshot to it.
    """
    text = DOCKERFILE.read_text(encoding="utf-8")
    lines = [line for line in text.splitlines()
             if line.strip().upper().startswith("VOLUME")]
    assert not lines, (
        "a VOLUME instruction makes /artifacts always look mounted: {}"
        .format(lines))
