"""The demo runner must not supply an acknowledgement the user omitted."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest


RUNNER = Path(__file__).resolve().parents[2] / "run.sh"


@pytest.mark.parametrize("accepted", [False, True])
def test_runner_passes_yahoo_acknowledgement_only_when_requested(
        tmp_path, accepted):
    """Drive argument parsing and setup, stopping before any real install."""
    runner = tmp_path / "run.sh"
    shutil.copyfile(RUNNER, runner)
    installer = tmp_path / "install.sh"
    installer.write_text(
        '#!/bin/bash\n'
        'printf "%s\\n" "$@" > "$OPTIONDESK_REVIEW_ARGS"\n'
        'exit 77\n', encoding="utf-8")
    installer.chmod(0o700)
    recorded = tmp_path / "installer-args.txt"
    env = dict(os.environ, OPTIONDESK_REVIEW_ARGS=str(recorded),
               OPTIONDESK_PREFIX=str(tmp_path / "prefix"))
    command = ["/bin/bash", str(runner), "--reinstall", "--no-dashboard",
               "--no-open", "--out-dir", str(tmp_path / "artifacts")]
    if accepted:
        command.append("--accept-yahoo-terms")

    result = subprocess.run(command, env=env, capture_output=True,
                            text=True, timeout=10)

    assert result.returncode == 1, result.stderr
    assert "the installer did not finish" in result.stderr
    passed = recorded.read_text(encoding="utf-8").splitlines()
    assert "--yes" in passed
    assert ("--accept-yahoo-terms" in passed) is accepted
