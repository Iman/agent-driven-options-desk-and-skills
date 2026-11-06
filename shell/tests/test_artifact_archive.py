"""An artifact that gets replaced must not simply disappear.

WHAT WOULD BREAK. Filenames are keyed by underlying and expiry, so pulling
the same chain twice replaced the first one outright. Every number quoted
from an artifact, in a report, a document or a conversation, became
unreproducible the moment anyone refreshed. Nothing warned, because a
replaced file and a never-written one look identical afterwards.

The live name deliberately stays the same. Timestamping it would give the
same history and break every consumer that resolves the newest artifact by
name: the dashboard, `expiries`, the plan reuse in `compare`, and the
graph's stage check. The timestamp goes on the outgoing copy instead.
"""

import json
import os

import pytest

from optiondesk.artifacts import (
    ARCHIVE_DIRNAME,
    archive_existing,
    envelope,
    write_json,
)
from optiondesk.contracts import CHAIN_SNAPSHOT
from optiondesk.cli.plots import _write_png


@pytest.fixture(params=["json", "png"])
def writer(request):
    if request.param == "json":
        return lambda payload, root: write_json(payload, "chain_TEST.json", root)
    return lambda payload, root: _write_png(json.dumps(payload).encode(), "plot_TEST.png", root)


def test_failed_replacement_preserves_the_live_artifact(tmp_path, monkeypatch, writer):
    path = writer({"spot": 100}, tmp_path)
    previous = path.read_bytes()
    replace = os.replace

    def fail_commit(source, target):
        if str(source).endswith(".tmp"):
            raise OSError("injected replacement failure")
        return replace(source, target)

    monkeypatch.setattr(os, "replace", fail_commit)
    with pytest.raises(OSError, match="injected"):
        writer({"spot": 101}, tmp_path)
    assert path.exists()
    assert path.read_bytes() == previous
    assert not list(tmp_path.glob("*.tmp"))


def test_same_timestamp_keeps_each_distinct_version(tmp_path, monkeypatch, writer):
    monkeypatch.setattr("optiondesk.artifacts._archive_stamp", lambda path: "same-time")
    for spot in (100, 101, 102):
        path = writer({"spot": spot}, tmp_path)
    retained = [path] + list((tmp_path / ARCHIVE_DIRNAME).rglob("*" + path.suffix))
    assert sorted(json.loads(p.read_bytes())["spot"] for p in retained) == [100, 101, 102]


def _payload(spot, generated=None):
    meta = envelope(schema=CHAIN_SNAPSHOT, tool="test", provider_used="stub")
    if generated:
        meta["generated_utc"] = generated
    return {"meta": meta, "underlying": "TEST", "spot": spot}


def test_the_replaced_artifact_is_kept(tmp_path):
    write_json(_payload(100.0, "2026-08-30T15:12:04Z"), "chain_TEST.json",
               tmp_path)
    write_json(_payload(101.0, "2026-08-30T19:41:00Z"), "chain_TEST.json",
               tmp_path)

    live = json.loads((tmp_path / "chain_TEST.json").read_text())
    assert live["spot"] == 101.0, "the newest artifact must be the live one"

    archived = sorted((tmp_path / ARCHIVE_DIRNAME).rglob("*.json"))
    assert len(archived) == 1, "the replaced artifact was not kept"
    assert json.loads(archived[0].read_text())["spot"] == 100.0


def test_the_live_name_never_changes(tmp_path):
    """Every consumer resolves artifacts by this name. It is a contract."""
    for spot in (100.0, 101.0, 102.0):
        path = write_json(_payload(spot), "chain_TEST.json", tmp_path)
        assert path.name == "chain_TEST.json"
    assert sorted(p.name for p in tmp_path.glob("*.json")) == [
        "chain_TEST.json"]


def test_the_archived_copy_is_named_for_when_it_was_generated(tmp_path):
    """Not for when the bytes landed: those differ whenever a file moves."""
    write_json(_payload(100.0, "2026-08-30T15:12:04Z"), "chain_TEST.json",
               tmp_path)
    write_json(_payload(101.0), "chain_TEST.json", tmp_path)

    archived = sorted((tmp_path / ARCHIVE_DIRNAME).rglob("*.json"))[0]
    assert "20260830T151204Z" in archived.name, archived.name
    assert archived.name.startswith("chain_TEST_")


def test_writing_identical_bytes_archives_nothing(tmp_path):
    """Re-running a command is not a new measurement.

    Without this the archive fills with copies of one answer, and the
    directory that exists to make history findable makes it harder to find.
    """
    payload = _payload(100.0, "2026-08-30T15:12:04Z")
    write_json(payload, "chain_TEST.json", tmp_path)
    write_json(payload, "chain_TEST.json", tmp_path)
    assert not (tmp_path / ARCHIVE_DIRNAME).exists()


def test_the_archive_can_be_turned_off(tmp_path, monkeypatch):
    monkeypatch.setenv("OPTIONDESK_ARCHIVE", "0")
    write_json(_payload(100.0), "chain_TEST.json", tmp_path)
    write_json(_payload(101.0), "chain_TEST.json", tmp_path)
    assert not (tmp_path / ARCHIVE_DIRNAME).exists()


def test_an_archive_that_cannot_be_written_does_not_lose_the_write(tmp_path):
    """Keeping history must never cost you the artifact you asked for.

    If the archive move fails, for a permission or a full disk, the write
    still has to land. A history feature that can eat the present is worse
    than no history feature.
    """
    write_json(_payload(100.0), "chain_TEST.json", tmp_path)
    blocker = tmp_path / ARCHIVE_DIRNAME
    blocker.write_text("not a directory", encoding="utf-8")

    write_json(_payload(101.0), "chain_TEST.json", tmp_path)
    live = json.loads((tmp_path / "chain_TEST.json").read_text())
    assert live["spot"] == 101.0


def test_archive_existing_on_a_missing_file_is_quiet(tmp_path):
    assert archive_existing(tmp_path / "nothing.json") is None


def test_the_archive_is_not_mistaken_for_an_artifact(tmp_path):
    """The directory sits beside the artifacts and must not be read as one.

    Everything that lists artifacts globs `*.json` in the artifact
    directory, not recursively, so the archive is invisible to it. If that
    ever changes, yesterday's chain starts appearing as today's.
    """
    write_json(_payload(100.0), "chain_TEST.json", tmp_path)
    write_json(_payload(101.0), "chain_TEST.json", tmp_path)
    assert [p.name for p in tmp_path.glob("*.json")] == ["chain_TEST.json"]
