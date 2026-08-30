"""Documented figures must still match the artifacts they were read from.

WHAT WOULD BREAK. Numbers measured from real artifacts went into the
documentation, and the artifacts they came from are keyed by underlying and
expiry, so the next pull replaced them. The chain behind "595 solved, 12
refused" reported 590 and 17 six hours later. The sentence stayed true of
the measurement and stopped being provable from anything on disk, and there
was no way to tell the difference between a figure that was carefully
measured and one that was remembered.

docs/evidence.json records each figure with the artifact it came from, when
that artifact was generated, and which provider answered. Derived numbers
only: no provider data is reproduced, because this project tells its own
users that redistribution is governed by the provider's terms and should
not then ship a chain.
"""

import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
EVIDENCE = ROOT / "docs" / "evidence.json"


@pytest.fixture(scope="module")
def figures():
    if not EVIDENCE.exists():
        pytest.skip("no evidence file recorded")
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))["figures"]


def test_every_recorded_sentence_is_still_in_its_document(figures):
    """An edit that rewords the sentence must not orphan the evidence."""
    missing = []
    for key, entry in figures.items():
        for document, sentence in entry["documents"].items():
            text = (ROOT / document).read_text(encoding="utf-8")
            if sentence not in text:
                missing.append("{}: {} lost {!r}".format(key, document,
                                                         sentence))
    assert not missing, (
        "the documentation moved away from its recorded evidence. Re-record "
        "with scripts/evidence.py or restore the wording: {}".format(missing))


def test_every_recorded_figure_agrees_with_its_sentence(figures):
    """The number in the prose must be the number in the artifact."""
    wrong = []
    for key, entry in figures.items():
        value = entry["value"]
        for document, sentence in entry["documents"].items():
            written = [float(n) for n in re.findall(r"\d+\.?\d*", sentence)]
            if isinstance(value, int):
                ok = float(value) in written
            else:
                ok = any(abs(n - value) < 1e-9 or abs(n - value * 100) <= 0.5
                         for n in written)
            if not ok:
                wrong.append("{}: {!r} does not carry {}".format(
                    key, sentence, value))
    assert not wrong, wrong


def test_every_figure_names_the_artifact_and_when_it_was_generated(figures):
    """Provenance is the point. A bare number proves nothing."""
    for key, entry in figures.items():
        assert entry.get("artifact"), "{} names no artifact".format(key)
        assert entry.get("generated_utc"), (
            "{} does not say when it was measured".format(key))
        assert "provider_used" in entry, (
            "{} does not say who answered".format(key))
        assert "degraded" in entry, (
            "{} does not say whether the source was degraded".format(key))


def test_no_provider_data_is_committed_with_the_evidence(figures):
    """Derived numbers only.

    LICENSES.md tells the reader that redistribution is governed by the
    provider's terms, and DISCLAIMER.md tells them to check before storing
    or redistributing. Shipping a chain snapshot here would have this
    project do the thing its own documents warn about.
    """
    raw = EVIDENCE.read_text(encoding="utf-8")
    assert len(raw) < 20000, (
        "the evidence file is large enough to be carrying market data "
        "rather than figures")
    for forbidden in ("contracts", "strike", "bid", "ask"):
        assert '"{}":'.format(forbidden) not in raw, (
            "{} looks like provider data rather than a derived "
            "figure".format(forbidden))


# --------------------------------------------------------- the recorder

def _load_recorder():
    """scripts/evidence.py, loaded as a module without running it."""
    import importlib.util

    path = ROOT / "scripts" / "evidence.py"
    if not path.exists():
        pytest.skip("evidence.py not present")
    spec = importlib.util.spec_from_file_location("desk_evidence", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _chain(spot, generated, with_iv):
    return {
        "meta": {"generated_utc": generated, "provider_used": "stub",
                 "degraded": False},
        "underlying": "TEST", "spot": spot,
        "counts": {"with_iv": with_iv, "without_iv": 3},
        "contracts": [{"strike": 1.0}] * 10,
    }


def test_a_pinned_claim_reads_the_measurement_it_names(tmp_path,
                                                       monkeypatch):
    """The newest artifact with the same name is a different measurement.

    This is the whole reason the file exists. A documented sentence
    describes one pull; the artifact carrying that filename tomorrow
    describes another. Recording the newest would make the evidence agree
    with whatever happened last and prove nothing about the sentence.
    """
    import json as _json

    recorder = _load_recorder()
    live = tmp_path / "chain_TEST.json"
    live.write_text(_json.dumps(_chain(101.0, "2026-08-30T19:41:00Z", 590)),
                    encoding="utf-8")
    archive = tmp_path / "archive" / "2026-08-30"
    archive.mkdir(parents=True)
    (archive / "chain_TEST_20260830T141217Z.json").write_text(
        _json.dumps(_chain(100.0, "2026-08-30T14:12:17Z", 595)),
        encoding="utf-8")

    monkeypatch.setattr(recorder, "_artifacts_dir", lambda: tmp_path)

    pinned = recorder._find_artifact("chain_TEST.json",
                                     "2026-08-30T14:12:17Z")
    assert pinned is not None, "the pinned measurement was not found"
    assert _json.loads(pinned.read_text())["counts"]["with_iv"] == 595, (
        "the recorder read the newest artifact instead of the one the "
        "claim pins")

    newest = recorder._find_artifact("chain_TEST.json")
    assert _json.loads(newest.read_text())["counts"]["with_iv"] == 590


def test_a_pin_that_matches_nothing_is_reported_not_guessed(tmp_path,
                                                            monkeypatch):
    """Falling back to the newest would silently record the wrong number."""
    import json as _json

    recorder = _load_recorder()
    (tmp_path / "chain_TEST.json").write_text(
        _json.dumps(_chain(101.0, "2026-08-30T19:41:00Z", 590)),
        encoding="utf-8")
    monkeypatch.setattr(recorder, "_artifacts_dir", lambda: tmp_path)

    assert recorder._find_artifact("chain_TEST.json",
                                   "2020-01-01T00:00:00Z") is None
