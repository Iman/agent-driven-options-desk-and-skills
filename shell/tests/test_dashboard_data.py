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


# --------------------------------------------------------------------------
# The surface, the premium and the condor set. Each reaches across every
# expiry on disk, which is the part that a per-group collector gets wrong.
# --------------------------------------------------------------------------


def chain_with(spot, days, quotes):
    """A chain artifact carrying one contract per (strike, type) in quotes."""
    contracts = []
    for strike, kind, iv in quotes:
        contracts.append({"symbol": "X", "type": kind, "strike": strike,
                          "bid": 1.0, "ask": 1.2, "mid": 1.1, "volume": 1,
                          "open_interest": 1, "iv": iv})
    return {"spot": spot, "days_to_expiry": days, "contracts": contracts}


def test_the_surface_takes_the_out_of_the_money_side_at_each_strike(tmp_path):
    """Catches both sides of a strike landing in the same cell.

    A call and a put at one strike quote different volatilities. Plotting
    both puts two values at one coordinate, and whichever is drawn second
    silently wins. The rule is puts below spot and calls at or above it,
    and this pins it.
    """
    quotes = [(90.0, "put", 0.30), (90.0, "call", 0.99),
              (110.0, "call", 0.20), (110.0, "put", 0.88)]
    put(tmp_path, "chain", "TEST", "2026-09-18",
        **chain_with(100.0, 20.0, quotes))
    put(tmp_path, "chain", "TEST", "2026-10-16",
        **chain_with(100.0, 47.0, quotes))

    surface = data_module.collect(tmp_path, "TEST")["surface"]
    chosen = {(row[0], row[1]): row[2] for row in surface["points"]}
    assert chosen[(90.0, 20.0)] == 0.30, "below spot must be the put"
    assert chosen[(110.0, 20.0)] == 0.20, "above spot must be the call"
    assert 0.99 not in chosen.values() and 0.88 not in chosen.values()


def test_the_surface_needs_more_than_one_expiry(tmp_path):
    """Catches a single chain being offered as a surface.

    One expiry is a smile, and the smile already has its own panel. The
    page uses this None to decide whether to emit the canvas at all.
    """
    put(tmp_path, "chain", "TEST", "2026-09-18",
        **chain_with(100.0, 20.0, [(100.0, "call", 0.2)]))

    assert data_module.collect(tmp_path, "TEST")["surface"] is None


def test_the_surface_reaches_every_expiry_and_nothing_is_interpolated(
        tmp_path):
    """Catches the surface being filled out between listed strikes.

    Expiries list different strikes. A gap is a strike that is not listed,
    and inventing a volatility to square the grid would be inventing a
    number.
    """
    put(tmp_path, "chain", "TEST", "2026-09-18",
        **chain_with(100.0, 20.0,
                     [(99.0, "put", 0.31), (100.0, "call", 0.22),
                      (101.0, "call", 0.23)]))
    put(tmp_path, "chain", "TEST", "2026-10-16",
        **chain_with(100.0, 47.0, [(100.0, "call", 0.25)]))

    surface = data_module.collect(tmp_path, "TEST")["surface"]
    assert [row["days"] for row in surface["expiries"]] == [20.0, 47.0]
    # Three points for the near expiry, one for the far one. Not four each.
    assert len(surface["points"]) == 4
    far = [row for row in surface["points"] if row[1] == 47.0]
    assert [row[0] for row in far] == [100.0]


def simulation_artifact(realised, **extra):
    payload = {
        "underlying": "TEST", "expiry": None, "spot": 100.0,
        "history": {"annualised_volatility": realised, "observations": 500,
                    "first": "2024-08-29", "last": "2026-08-28",
                    "period": "2y"},
        "simulation": {"horizon_days": 14, "paths": 20000,
                       "fan": [{"day": 1, "p5": 97.0, "p25": 99.0,
                                "p50": 100.0, "p75": 101.0, "p95": 103.0}]},
    }
    payload.update(extra)
    return payload


def exposure_with_smile(atm_iv, days):
    return {"days_to_expiry": days,
            "smile": {"atm_iv": atm_iv, "risk_reversal": 0.01,
                      "butterfly": 0.005, "expected_move": 5.0}}


def test_the_premium_is_the_gap_between_two_recorded_numbers(tmp_path):
    """Catches the gap being computed from anything but the artifacts.

    Implied is each expiry's own at-the-money volatility, realised is the
    one figure the simulation recorded. The difference is arithmetic on
    two numbers that are both on disk, and nothing else.
    """
    put(tmp_path, "exposure", "TEST", "2026-09-18",
        **exposure_with_smile(0.20, 19.0))
    put(tmp_path, "exposure", "TEST", "2026-10-16",
        **exposure_with_smile(0.25, 47.0))
    write_json(simulation_artifact(0.30), "simulation_TEST_14d.json",
               tmp_path)

    premium = data_module.collect(tmp_path, "TEST")["variance_premium"]
    assert premium["realised"] == 0.30
    gaps = {row["days"]: row["gap"] for row in premium["rows"]}
    assert gaps[19.0] == pytest.approx(0.20 - 0.30)
    assert gaps[47.0] == pytest.approx(0.25 - 0.30)
    assert premium["history"]["period"] == "2y"


def test_there_is_no_premium_without_a_realised_figure(tmp_path):
    """Catches a premium drawn against a realised volatility that is absent.

    Without the simulation there is no realised number anywhere on disk,
    and the honest answer is no panel rather than a substitute.
    """
    put(tmp_path, "exposure", "TEST", "2026-09-18",
        **exposure_with_smile(0.20, 19.0))
    put(tmp_path, "exposure", "TEST", "2026-10-16",
        **exposure_with_smile(0.25, 47.0))

    assert data_module.collect(tmp_path, "TEST")["variance_premium"] is None


def condor_plan(shorts, longs):
    legs = [{"kind": "put", "side": "short", "strike": shorts[0]},
            {"kind": "call", "side": "short", "strike": shorts[1]},
            {"kind": "put", "side": "long", "strike": longs[0]},
            {"kind": "call", "side": "long", "strike": longs[1]}]
    return {"legs": legs, "days_to_expiry": 19.0}


def comparison_with(strategy, ror, pop):
    return {"rows": [{"strategy": strategy, "expected_return_on_risk": ror,
                      "probability_of_profit": pop, "capital_at_risk": 8.0,
                      "net_cash": 2.0, "max_loss": -8.0,
                      "friction_verdict": "ok", "rank": 1}]}


def test_condor_width_is_measured_off_the_plans_own_legs(tmp_path):
    """Catches the width being taken from anywhere but the strikes.

    The distance between the shorts, and the wing distance beyond each of
    them, are properties of the four strikes in the artifact. Nothing else
    on disk records them.
    """
    put(tmp_path, "strategy", "TEST", "2026-09-18", strategy="iron_condor",
        **condor_plan((90.0, 110.0), (85.0, 115.0)))
    put(tmp_path, "comparison", "TEST", "2026-09-18",
        **comparison_with("iron_condor", 0.12, 0.7))

    condors = data_module.collect(tmp_path, "TEST")["condors"]
    assert len(condors) == 1
    assert condors[0]["width"] == 20.0
    assert condors[0]["wing"] == 5.0
    assert condors[0]["expected_return_on_risk"] == 0.12


def test_a_condor_is_never_scored_against_another_expirys_comparison(
        tmp_path):
    """Catches a plan borrowing the ordering of a different expiry.

    Two expiries are two different chains. A September condor scored by
    October's comparison would look entirely plausible and be wrong, which
    is the same failure the group keying exists to prevent.
    """
    put(tmp_path, "strategy", "TEST", "2026-09-18", strategy="iron_condor",
        **condor_plan((90.0, 110.0), (85.0, 115.0)))
    put(tmp_path, "comparison", "TEST", "2026-10-16",
        **comparison_with("iron_condor", 0.12, 0.7))

    assert data_module.collect(tmp_path, "TEST")["condors"] == []


def test_a_structure_with_one_short_strike_has_no_width_and_is_left_out(
        tmp_path):
    """Catches a vertical spread being drawn at zero width.

    Zero width means the shorts sit on one strike, which is a butterfly. A
    structure with a single short leg has no distance between shorts at
    all, and putting it at zero would say something untrue about it.
    """
    legs = [{"kind": "put", "side": "short", "strike": 95.0},
            {"kind": "put", "side": "long", "strike": 90.0}]
    put(tmp_path, "strategy", "TEST", "2026-09-18",
        strategy="bear_put_spread", legs=legs, days_to_expiry=19.0)
    put(tmp_path, "comparison", "TEST", "2026-09-18",
        **comparison_with("bear_put_spread", 0.2, 0.4))

    assert data_module.collect(tmp_path, "TEST")["condors"] == []
