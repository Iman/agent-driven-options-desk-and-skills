import json

from optiondesk.artifacts import (
    DISCLAIMER,
    envelope,
    latest,
    read_json,
    write_json,
)


def test_envelope_carries_provenance_and_disclaimer():
    meta = envelope("s/v1", "unit test", "fixture", degraded=True,
                    degraded_reason="because")
    assert meta["schema"] == "s/v1"
    assert meta["provider_used"] == "fixture"
    assert meta["degraded"] is True
    assert meta["degraded_reason"] == "because"
    assert "not investment advice" in meta["disclaimer"]
    assert meta["disclaimer"] == DISCLAIMER
    assert meta["generated_utc"].endswith("+00:00")


def test_write_is_atomic_and_leaves_no_temp_file(tmp_path):
    path = write_json({"a": 1}, "x.json", tmp_path)
    assert path.exists()
    assert list(tmp_path.glob("*.tmp")) == []
    assert read_json(path) == {"a": 1}
    assert json.loads(path.read_text())["a"] == 1


def test_latest_returns_most_recent_match(tmp_path):
    import os
    import time
    first = write_json({"n": 1}, "chain_a.json", tmp_path)
    time.sleep(0.01)
    second = write_json({"n": 2}, "chain_b.json", tmp_path)
    os.utime(second, None)
    assert latest("chain_*.json", tmp_path) == second
    assert latest("nothing_*.json", tmp_path) is None
    assert first.exists()


def test_notes_are_separate_from_degradation():
    # The two must never be conflated: a note is an observation, a
    # degradation is a warning about output quality.
    meta = envelope("s/v1", "unit test", "fixture",
                    notes=["23 contracts carry no implied volatility"])
    assert meta["degraded"] is False
    assert meta["degraded_reason"] is None
    assert meta["notes"] == ["23 contracts carry no implied volatility"]
