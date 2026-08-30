"""optiondesk expiries: what the provider lists, and what is already local."""

import json

import pytest

from optiondesk.artifacts import write_json
from optiondesk.cli import expiries as expiries_cmd
from optiondesk.providers.base import ProviderDataError

from marks import needs_engine


def expiries_args(args_factory, tmp_path, **overrides):
    kwargs = {"symbol": None, "provider": None, "out_dir": str(tmp_path)}
    kwargs.update(overrides)
    return args_factory(**kwargs)


@needs_engine
def test_listing_what_is_on_disk_reaches_no_provider(
        stub_provider, chain_snapshot, args_factory, tmp_path):
    """Catches a local inventory quietly making a network call.

    Omitting the symbol is documented as the offline path, so the stub is
    asserted never to have been asked anything.
    """
    stub = stub_provider()
    write_json(chain_snapshot(), "chain_TEST_2026-09-18.json", tmp_path)
    result = expiries_cmd.run(expiries_args(args_factory, tmp_path))

    assert stub.calls == []
    assert result["on_disk"] == [
        {"underlying": "TEST", "expiry": "2026-09-18", "spot": 100.0,
         "have": ["chain"], "strategies": []}]
    assert "optiondesk expiries QQQ" in result["hint"]


@needs_engine
def test_what_is_already_pulled_is_marked_against_the_listing(
        stub_provider, chain_snapshot, args_factory, tmp_path):
    """Catches the on_disk flag being wrong, which is the whole point.

    The command exists to answer which listed expiry a user still has to
    pull. A flag that is always false, or always true, answers nothing.
    """
    stub_provider(expiries=["2026-09-18", "2026-10-16", "2026-11-20"])
    write_json(chain_snapshot(expiry="2026-10-16"),
               "chain_TEST_2026-10-16.json", tmp_path)
    result = expiries_cmd.run(expiries_args(args_factory, tmp_path,
                                            symbol="test"))

    assert result["underlying"] == "TEST"
    assert result["listed"] == 3
    assert result["already_pulled"] == ["2026-10-16"]
    marked = {row["expiry"]: row["on_disk"] for row in result["expiries"]}
    assert marked == {"2026-09-18": False, "2026-10-16": True,
                      "2026-11-20": False}
    assert result["next"] == "optiondesk chain TEST --expiry 2026-09-18"


def test_days_to_expiry_is_computed_and_ordered(stub_provider, args_factory,
                                                tmp_path):
    """Catches the day count losing its sign or its order.

    A past expiry has to come back negative rather than being clamped, so a
    caller can refuse it instead of pricing against a floor.
    """
    stub_provider(expiries=["2020-01-17", "2099-12-18"])
    result = expiries_cmd.run(expiries_args(args_factory, tmp_path,
                                            symbol="TEST"))
    days = [row["days_to_expiry"] for row in result["expiries"]]

    assert days[0] < 0
    assert days[1] > 0


def test_an_unparseable_expiry_reports_no_day_count_rather_than_guessing(
        stub_provider, args_factory, tmp_path):
    """Catches a malformed date being turned into a plausible number.

    A guessed day count would price contracts against a horizon nobody
    supplied.
    """
    stub_provider(expiries=["not-a-date", "2099-12-18"])
    result = expiries_cmd.run(expiries_args(args_factory, tmp_path,
                                            symbol="TEST"))

    assert result["expiries"][0] == {"expiry": "not-a-date",
                                     "days_to_expiry": None,
                                     "on_disk": False}


def test_an_unreadable_artifact_is_skipped_not_fatal(args_factory, tmp_path):
    """Catches one corrupt file taking the whole inventory down.

    A truncated write from an interrupted run must not stop a user seeing
    everything else they have.
    """
    (tmp_path / "chain_BAD_2026-09-18.json").write_text("{not json",
                                                        encoding="utf-8")
    write_json({"underlying": "GOOD", "expiry": "2026-09-18", "spot": 1.0},
               "chain_GOOD_2026-09-18.json", tmp_path)

    result = expiries_cmd.run(expiries_args(args_factory, tmp_path))
    assert [entry["underlying"] for entry in result["on_disk"]] == ["GOOD"]


def test_files_that_are_not_artifacts_are_ignored(args_factory, tmp_path):
    """Catches the inventory claiming things it did not produce.

    The artifact directory is a directory a user can put files in.
    """
    write_json({"underlying": "TEST", "expiry": "2026-09-18"},
               "notes_TEST_2026-09-18.json", tmp_path)
    (tmp_path / "README.txt").write_text("hello", encoding="utf-8")

    result = expiries_cmd.run(expiries_args(args_factory, tmp_path))
    assert result["on_disk"] == []


def test_an_empty_directory_reports_nothing_rather_than_failing(
        args_factory, tmp_path):
    """Catches a fresh install erroring instead of saying it has nothing."""
    result = expiries_cmd.run(expiries_args(args_factory, tmp_path))
    assert result["on_disk"] == []
    assert result["artifact_dir"] == str(tmp_path)


def test_a_missing_directory_reports_nothing_rather_than_failing(
        args_factory, tmp_path):
    """Catches the very first run, before the directory has been created."""
    missing = tmp_path / "never-created"
    assert expiries_cmd.on_disk(str(missing)) == {}


def test_strategy_plans_are_listed_under_their_group(args_factory, tmp_path):
    """Catches plans being lost from the inventory or attached to the wrong
    expiry.

    The inventory is what tells a user which structures they have already
    built for which expiry.
    """
    for name in ("iron_condor", "straddle"):
        write_json({"underlying": "TEST", "expiry": "2026-09-18",
                    "spot": 100.0, "strategy": name},
                   "strategy_TEST_{}_2026-09-18.json".format(name), tmp_path)
    write_json({"underlying": "TEST", "expiry": "2026-10-16", "spot": 100.0,
                "strategy": "long_call"},
               "strategy_TEST_long_call_2026-10-16.json", tmp_path)

    result = expiries_cmd.run(expiries_args(args_factory, tmp_path))
    by_expiry = {entry["expiry"]: entry["strategies"]
                 for entry in result["on_disk"]}
    assert by_expiry["2026-09-18"] == ["iron_condor", "straddle"]
    assert by_expiry["2026-10-16"] == ["long_call"]


def test_a_provider_that_raises_is_not_swallowed(stub_provider, args_factory,
                                                 tmp_path):
    """Catches a listing failure being reported as an empty listing.

    No expiries and a failed lookup are different facts.
    """
    stub_provider(raises=ProviderDataError("TEST: no option expirations "
                                           "listed"))
    with pytest.raises(ProviderDataError) as excinfo:
        expiries_cmd.run(expiries_args(args_factory, tmp_path,
                                       symbol="TEST"))
    assert "no option expirations" in str(excinfo.value)
