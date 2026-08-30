"""The dispatcher: argument wiring, the single error shape, and exit codes."""

import argparse
import json

import pytest

from optiondesk import __version__
from optiondesk.artifacts import write_json
from optiondesk.cli import __main__ as main_module

from conftest import needs_engine


def subcommands(parser):
    action = next(a for a in parser._actions
                  if isinstance(a, argparse._SubParsersAction))
    return set(action.choices)


def test_every_subcommand_has_a_handler():
    """Catches a subcommand being added to the parser and nowhere else.

    argparse accepts the command, then HANDLERS raises KeyError, which the
    wrapper reports as an error message rather than as the missing wiring
    it is. The gap only shows up when someone runs the new command.
    """
    assert subcommands(main_module.build_parser()) == set(main_module.HANDLERS)


def test_every_handler_is_reachable_from_the_command_line():
    """Catches a handler that no subcommand can ever dispatch to.

    Dead entries in the table make it a poor record of what the tool does.
    """
    assert set(main_module.HANDLERS) <= subcommands(
        main_module.build_parser())


def test_a_failure_is_reported_in_one_json_shape(capsys, tmp_path):
    """Catches a traceback reaching stdout.

    An agent parsing stdout must not have to tell a Python traceback from a
    result, so every failure leaves as the same JSON object.
    """
    code = main_module.main(["exposure", "--out-dir", str(tmp_path)])
    printed = json.loads(capsys.readouterr().out)

    assert code == 1
    assert printed["error"] in ("FileNotFoundError", "EngineUnavailable")
    assert printed["message"]
    assert set(printed) == {"error", "message"}


@needs_engine
def test_an_unknown_strategy_leaves_as_an_error_not_a_result(
        snapshot, capsys, tmp_path):
    """Catches an unrecognised name being answered with a plausible plan.

    A real snapshot is on disk, so the failure is the name and nothing else.
    """
    write_json(snapshot, "chain_TEST_2026-09-18.json", tmp_path)
    code = main_module.main(["strategy", "no_such_strategy",
                             "--out-dir", str(tmp_path)])
    printed = json.loads(capsys.readouterr().out)

    assert code == 1
    assert printed["error"] == "KeyError"
    assert "no_such_strategy" in printed["message"]


@needs_engine
def test_a_successful_run_prints_its_result_and_exits_zero(
        stub_provider, provider_chain, capsys, tmp_path):
    """Catches a result that stdout cannot carry.

    default=str keeps a Path or a datetime from turning a good run into a
    serialisation failure.
    """
    stub_provider(chain=provider_chain())
    code = main_module.main(["chain", "TEST", "--out-dir", str(tmp_path)])
    printed = json.loads(capsys.readouterr().out)

    assert code == 0
    assert printed["underlying"] == "TEST"
    assert printed["provider_used"] == "stub"
    assert printed["artifact"].endswith("chain_TEST_2026-09-18.json")


def test_doctor_reports_engine_providers_and_the_disclaimer(capsys):
    """Catches doctor losing the fields a user runs it for.

    It is the command someone runs when nothing works, so it has to say
    what is installed, what can answer, and which keys are present.
    """
    code = main_module.main(["doctor"])
    printed = json.loads(capsys.readouterr().out)

    assert code == 0
    assert printed["shell_version"] == __version__
    assert set(printed["engine"]) >= {"available", "package", "version",
                                      "license"}
    assert "yahoo" in printed["providers"]
    assert "yahoo" in printed["credentials"]
    assert "not investment advice" in printed["disclaimer"]


def test_doctor_never_prints_a_credential(capsys, monkeypatch):
    """Catches a key being echoed by the command users paste into issues."""
    monkeypatch.setenv("TRADIER_API_KEY", "super-secret-token")
    main_module.main(["doctor"])
    out = capsys.readouterr().out

    assert "super-secret-token" not in out
    assert json.loads(out)["credentials"]["tradier"]["key_present"] is True


def test_version_and_help_exit_cleanly(capsys):
    """Catches --version being swallowed by the error wrapper."""
    with pytest.raises(SystemExit) as excinfo:
        main_module.main(["--version"])
    assert excinfo.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_no_command_is_rejected():
    """Catches the dispatcher running something when nothing was asked for."""
    with pytest.raises(SystemExit) as excinfo:
        main_module.main([])
    assert excinfo.value.code != 0


def test_an_unknown_command_is_rejected():
    """Catches an unrecognised command being routed somewhere."""
    with pytest.raises(SystemExit) as excinfo:
        main_module.main(["not_a_command"])
    assert excinfo.value.code != 0
