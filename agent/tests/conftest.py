"""Shared fixtures for the agent layer.

Nothing here touches the network or the real artifact directory. The graph
tests drive the loop with injected runners over a temporary store, which is
the only way to exercise the loop's exits deterministically: the real
runners reach a provider, and a provider that is merely slow would turn a
loop bound into a flaky test rather than a proved one.
"""

import json

import pytest

from optiondesk_agent.artifacts import ArtifactStore


@pytest.fixture
def store(tmp_path):
    """An ArtifactStore over an empty temporary directory."""
    return ArtifactStore(tmp_path)


@pytest.fixture
def write_artifact(tmp_path):
    """Write one artifact the way the store expects to find it.

    The kind comes from the filename prefix, because that is how
    ArtifactStore.records identifies an artifact. A fixture that named its
    files any other way would be writing artifacts the store cannot see,
    and every test built on it would pass against an empty directory.
    """
    def write(kind, underlying="SPY", expiry=None, degraded=False,
              degraded_reason=None, **extra):
        payload = {
            "underlying": underlying,
            "expiry": expiry,
            "meta": {"generated_utc": "2026-08-30T12:00:00+00:00",
                     "degraded": degraded,
                     "degraded_reason": degraded_reason},
        }
        payload.update(extra)
        path = tmp_path / "{}_{}_{}.json".format(kind, underlying,
                                                 expiry or "na")
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    return write
