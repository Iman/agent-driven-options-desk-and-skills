"""Dashboard collection: grouping, selection, and keeping expiries apart.

Selection is tested here rather than through the HTML, because a group that
mixes two expiries is wrong whether or not it renders.
"""

import time

import pytest

from optiondesk.artifacts import write_json
from optiondesk.dashboard import data as data_module


def artifact(kind, underlying, expiry, **extra):
    payload = {"underlying": underlying, "expiry": expiry, "spot": 100.0,
               "meta": {"generated_utc": "2026-08-28T12:00:00+00:00"}}
    payload.update(extra)
    return payload


def put(tmp_path, kind, underlying, expiry, **extra):
    name = "{}_{}_{}.json".format(kind, underlying, expiry)
    if kind == "strategy":
        name = "strategy_{}_{}_{}.json".format(underlying,
                                               extra["strategy"], expiry)
    path = write_json(artifact(kind, underlying, expiry, **extra), name,
                      tmp_path)
    # Distinct modification times, because ordering is by mtime and a
    # same-millisecond tie would make the assertions depend on the
    # filesystem's clock resolution rather than on the code.
    time.sleep(0.01)
    return path


def test_groups_are_keyed_by_underlying_and_expiry(tmp_path):
    """Catches two expiries collapsing into one group.

    The pair is what a reader chooses between; merging them puts a
    September ladder next to an October chain under one heading.
    """
    put(tmp_path, "chain", "TEST", "2026-09-18")
    put(tmp_path, "chain", "TEST", "2026-10-16")
    put(tmp_path, "chain", "OTHER", "2026-09-18")

    groups = data_module.index(tmp_path)
    keys = {(g["underlying"], g["expiry"]) for g in groups}
    assert keys == {("TEST", "2026-09-18"), ("TEST", "2026-10-16"),
                    ("OTHER", "2026-09-18")}


def test_a_group_never_takes_an_artifact_from_another_expiry(tmp_path):
    """Catches a missing artifact being filled in from a different expiry.

    This is the specific failure the module exists to prevent: an October
    exposure profile shown under a September heading looks entirely
    plausible and is entirely wrong.
    """
    put(tmp_path, "chain", "TEST", "2026-09-18")
    put(tmp_path, "greeks", "TEST", "2026-09-18")
    put(tmp_path, "exposure", "TEST", "2026-10-16")

    collected = data_module.collect(tmp_path, "TEST", "2026-09-18")
    assert collected["selected"]["expiry"] == "2026-09-18"
    assert collected["ladder"]["expiry"] == "2026-09-18"
    # September has no exposure of its own, and October's must not stand in.
    assert collected["exposure"] is None
    assert collected["selected"]["have"] == ["chain", "greeks"]


def test_the_newest_artifact_of_a_kind_wins_within_a_group(tmp_path):
    """Catches a stale artifact being shown after a fresh run.

    Two runs of the same command for the same expiry write the same
    filename, but a renamed or copied older file must not outrank it.
    """
    put(tmp_path, "chain", "TEST", "2026-09-18", spot=1.0)
    newer = write_json(artifact("chain", "TEST", "2026-09-18", spot=2.0),
                       "chain_TEST_2026-09-18.json", tmp_path)

    groups = data_module.index(tmp_path)
    assert groups[0]["artifacts"]["chain"]["spot"] == 2.0
    assert groups[0]["paths"]["chain"] == str(newer)


def test_groups_are_ordered_newest_first(tmp_path):
    """Catches the default view landing on whatever was pulled first."""
    put(tmp_path, "chain", "OLD", "2026-09-18")
    put(tmp_path, "chain", "NEW", "2026-09-18")

    groups = data_module.index(tmp_path)
    assert [g["underlying"] for g in groups] == ["NEW", "OLD"]


def test_select_honours_the_named_underlying(tmp_path):
    """Catches a ticker click landing on a different ticker."""
    put(tmp_path, "chain", "TEST", "2026-09-18")
    put(tmp_path, "chain", "OTHER", "2026-09-18")
    groups = data_module.index(tmp_path)

    assert data_module.select(groups, "TEST")["underlying"] == "TEST"
    assert data_module.select(groups, "test")["underlying"] == "TEST"
    # Nothing named selects the most recently touched group.
    assert data_module.select(groups)["underlying"] == "OTHER"


def test_select_honours_the_named_expiry(tmp_path):
    """Catches an expiry link resolving to the newest expiry instead.

    Every view is addressable by query parameter, so a link that lands
    somewhere else makes the whole selector unreliable.
    """
    put(tmp_path, "chain", "TEST", "2026-09-18")
    put(tmp_path, "chain", "TEST", "2026-10-16")
    groups = data_module.index(tmp_path)

    assert data_module.select(groups, "TEST",
                              "2026-09-18")["expiry"] == "2026-09-18"
    assert data_module.select(groups, "TEST",
                              "2026-10-16")["expiry"] == "2026-10-16"
    # An underlying alone selects that underlying's newest expiry.
    assert data_module.select(groups, "TEST")["expiry"] == "2026-10-16"


def test_plans_are_gathered_per_group_and_deduplicated(tmp_path):
    """Catches the same structure appearing twice, or under the wrong expiry.

    The picker is built straight from this list.
    """
    put(tmp_path, "strategy", "TEST", "2026-09-18", strategy="iron_condor")
    put(tmp_path, "strategy", "TEST", "2026-09-18", strategy="straddle")
    put(tmp_path, "strategy", "TEST", "2026-10-16", strategy="long_call")

    collected = data_module.collect(tmp_path, "TEST", "2026-09-18")
    assert [p["strategy"] for p in collected["plans"]] == ["iron_condor",
                                                           "straddle"]
    assert collected["selected"]["plan_count"] == 2


def test_an_unreadable_artifact_is_skipped_not_fatal(tmp_path):
    """Catches one truncated file blanking the whole dashboard.

    An interrupted run is the ordinary way a half-written file appears.
    """
    (tmp_path / "chain_BAD_2026-09-18.json").write_text("{not json",
                                                        encoding="utf-8")
    put(tmp_path, "chain", "GOOD", "2026-09-18")

    groups = data_module.index(tmp_path)
    assert [g["underlying"] for g in groups] == ["GOOD"]


def test_an_artifact_without_an_underlying_is_skipped(tmp_path):
    """Catches a group keyed on None appearing in the picker."""
    write_json({"expiry": "2026-09-18", "spot": 1.0},
               "chain_NOTHING_2026-09-18.json", tmp_path)
    assert data_module.index(tmp_path) == []


def test_files_that_are_not_artifacts_are_ignored(tmp_path):
    """Catches unrelated JSON in the directory being rendered as a chain."""
    write_json({"underlying": "TEST", "expiry": "2026-09-18"},
               "notes_TEST_2026-09-18.json", tmp_path)
    assert data_module.index(tmp_path) == []


def test_an_empty_or_missing_directory_yields_no_groups(tmp_path):
    """Catches a fresh install failing instead of rendering an empty desk."""
    assert data_module.index(tmp_path) == []
    assert data_module.index(tmp_path / "never-created") == []


def test_collect_on_an_empty_directory_selects_nothing(tmp_path):
    """Catches the empty case losing a key the page reads unconditionally.

    render() indexes ladder, plans and series directly, so a missing key is
    a KeyError on the first page load of a fresh install.
    """
    collected = data_module.collect(tmp_path)
    assert collected["selected"] is None
    assert collected["ladder"] is None
    assert collected["plans"] == []
    assert collected["groups"] == []
    assert set(collected) >= {"artifact_dir", "ladder", "ladder_path",
                              "exposure", "exposure_path", "comparison",
                              "plans", "groups", "selected"}


def test_ladder_series_splits_by_type_and_sorts_by_strike(tmp_path):
    """Catches calls and puts being drawn on one line, or drawn unsorted.

    An unsorted series produces a smile chart that zigzags across the page.
    """
    ladder = {"rows": [
        {"type": "put", "strike": 110.0, "iv": 0.2, "delta": -0.3},
        {"type": "call", "strike": 110.0, "iv": 0.2, "delta": 0.3},
        {"type": "call", "strike": 90.0, "iv": 0.3, "delta": 0.8},
    ]}
    series = data_module.ladder_series(ladder)

    assert [row["strike"] for row in series["calls"]] == [90.0, 110.0]
    assert [row["strike"] for row in series["puts"]] == [110.0]
    assert series["calls"][0]["delta"] == 0.8


def test_ladder_series_of_nothing_is_two_empty_series():
    """Catches the no-ladder case returning None into the chart script."""
    assert data_module.ladder_series(None) == {"calls": [], "puts": []}
    assert data_module.ladder_series({}) == {"calls": [], "puts": []}


def test_a_simulation_belongs_to_the_underlying_not_to_one_expiry(tmp_path):
    """Catches a simulation being attached to a single expiry group.

    It is fitted to the underlying's own history and has no expiry of its
    own, so filing it under one would hide it from every other expiry of
    the same ticker.
    """
    put(tmp_path, "chain", "TEST", "2026-09-18")
    put(tmp_path, "chain", "TEST", "2026-10-16")
    write_json({"underlying": "TEST", "spot": 100.0, "meta": {},
                "posterior": {}, "simulation": {}},
               "simulation_TEST_5d.json", tmp_path)

    for expiry in ("2026-09-18", "2026-10-16"):
        collected = data_module.collect(tmp_path, "TEST", expiry)
        assert collected["selected"]["expiry"] == expiry
        assert collected["simulation"] is not None


def test_a_simulation_alone_is_not_offered_as_a_chain_view(tmp_path):
    """Catches the picker offering a group with no chain behind it.

    Selecting it would present an empty desk, because a simulation carries
    no ladder, no exposure and no plans.
    """
    write_json({"underlying": "TEST", "spot": 100.0, "meta": {},
                "posterior": {}, "simulation": {}},
               "simulation_TEST_5d.json", tmp_path)

    collected = data_module.collect(tmp_path)
    assert collected["groups"] == []
    assert collected["selected"] is None


def test_another_symbols_simulation_is_not_borrowed(tmp_path):
    """Catches one ticker's forward distribution being shown under another.

    The lookup deliberately reaches across expiry groups, so the symbol
    check is the only thing keeping two tickers apart.
    """
    put(tmp_path, "chain", "TEST", "2026-09-18")
    write_json({"underlying": "OTHER", "spot": 50.0, "meta": {},
                "posterior": {}, "simulation": {}},
               "simulation_OTHER_5d.json", tmp_path)

    collected = data_module.collect(tmp_path, "TEST")
    assert collected["selected"]["underlying"] == "TEST"
    assert collected["simulation"] is None
