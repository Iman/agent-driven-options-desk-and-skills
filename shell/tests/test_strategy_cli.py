"""optiondesk strategy: plans, unbounded outcomes, and the skip rules."""

import json

import pytest

from optiondesk.artifacts import read_json, write_json
from optiondesk.cli import strategy as strategy_cmd
from optiondesk.contracts import SCHEMA_FILES, STRATEGY_PLAN, validate

from marks import needs_engine

pytestmark = needs_engine


def strategy_args(args_factory, tmp_path, **overrides):
    kwargs = {"name": None, "snapshot": None, "size": 1.0,
              "underlying_entry": None, "list_only": False, "recommend": None,
              "vol_view": "neutral", "owns_underlying": False,
              "direction_unknown": False, "out_dir": str(tmp_path),
              # Added when time spreads landed: a second chain, which side
              # to build from, and how far a diagonal leans.
              "far_snapshot": None, "kind": "call", "offset": 0.03}
    kwargs.update(overrides)
    return args_factory(**kwargs)


def put_snapshot(chain_snapshot, tmp_path, **overrides):
    snapshot = chain_snapshot(**overrides)
    write_json(snapshot, "chain_{}_{}.json".format(
        snapshot["underlying"], snapshot["expiry"]), tmp_path)
    return snapshot


def test_plan_is_written_and_validates(chain_snapshot, args_factory,
                                       tmp_path):
    """Catches a plan that no longer satisfies strategy_plan/v1.

    The dashboard, the comparison and the simulation all read this artifact,
    so a payload the schema rejects has broken three consumers at once.
    """
    put_snapshot(chain_snapshot, tmp_path)
    result = strategy_cmd.run(strategy_args(args_factory, tmp_path,
                                            name="iron_condor"))

    assert result["built"] is True
    payload = read_json(result["artifact"])
    assert payload["meta"]["schema"] == STRATEGY_PLAN
    assert validate(payload, SCHEMA_FILES[STRATEGY_PLAN]) is payload
    assert payload["strategy"] == "iron_condor"
    assert len(payload["legs"]) == 4
    assert payload["payoff_curve"]["prices"]
    assert len(payload["payoff_curve"]["prices"]) == \
        len(payload["payoff_curve"]["pnl"])


def test_unbounded_gain_survives_the_round_trip_as_unlimited(
        chain_snapshot, args_factory, tmp_path):
    """Catches infinity being written as null, or as a large number.

    Null would erase the difference between an unbounded outcome and an
    unknown one; a big number would invent a ceiling that does not exist.
    The literal string has to be in the file on disk, not only in memory.
    """
    put_snapshot(chain_snapshot, tmp_path)
    result = strategy_cmd.run(strategy_args(args_factory, tmp_path,
                                            name="long_call"))

    assert result["max_gain"] == "unlimited"
    raw = open(result["artifact"], encoding="utf-8").read()
    assert '"max_gain": "unlimited"' in raw
    reloaded = json.loads(raw)
    assert reloaded["analysis"]["max_gain"] == "unlimited"
    # And the schema has to keep permitting it.
    assert validate(reloaded, SCHEMA_FILES[STRATEGY_PLAN]) is reloaded


def test_both_infinities_become_unlimited_and_finite_values_do_not():
    """Catches the sentinel leaking into ordinary numbers, or vice versa.

    A finite max loss quietly rewritten as a string would break every
    consumer that does arithmetic on it.
    """
    assert strategy_cmd._jsonable(float("inf")) == "unlimited"
    assert strategy_cmd._jsonable(float("-inf")) == "unlimited"
    assert strategy_cmd._jsonable(0.0) == 0.0
    assert strategy_cmd._jsonable(-123.5) == -123.5
    assert strategy_cmd._jsonable(None) is None


def test_a_leg_without_volatility_is_skipped_and_counted(
        chain_snapshot, args_factory, tmp_path):
    """Catches a defaulted volatility being used to complete the Greeks.

    The counted skip is the only thing that tells a reader the net Greeks
    describe fewer legs than the structure has. Filling the gap in would
    produce a complete and fictional risk profile.
    """
    put_snapshot(chain_snapshot, tmp_path, no_iv={(100.0, "call")})
    result = strategy_cmd.run(strategy_args(args_factory, tmp_path,
                                            name="long_call"))

    net = read_json(result["artifact"])["net_greeks"]
    assert net["legs_skipped_without_iv"] == 1
    assert net["legs_priced"] == 0
    assert any("no implied volatility" in note for note in result["notes"])


def test_priced_legs_produce_the_expected_sign(chain_snapshot, args_factory,
                                               tmp_path):
    """Catches the leg sign being dropped from the net Greek sum.

    A short leg that contributes with a long leg's sign turns a hedged
    structure into an unhedged one on paper.
    """
    put_snapshot(chain_snapshot, tmp_path)
    long_call = strategy_cmd.run(strategy_args(args_factory, tmp_path,
                                               name="long_call"))
    short_put = strategy_cmd.run(strategy_args(args_factory, tmp_path,
                                               name="cash_secured_put"))

    assert long_call["net_delta"] > 0
    assert long_call["net_theta"] < 0
    # A written put is long delta and collects decay.
    assert short_put["net_delta"] > 0
    assert short_put["net_theta"] > 0


def test_a_wide_spread_is_reported_as_friction(chain_snapshot, args_factory,
                                               tmp_path):
    """Catches the friction verdict never reaching the reader.

    A payoff computed at mid is not a payoff anyone gets, and a structure
    that cannot be traded at the quotes has to say so on the plan.
    """
    snapshot = chain_snapshot()
    for contract in snapshot["contracts"]:
        contract["bid"] = round(contract["mid"] * 0.2, 4)
        contract["ask"] = round(contract["mid"] * 1.8, 4)
    write_json(snapshot, "chain_TEST_2026-09-18.json", tmp_path)
    result = strategy_cmd.run(strategy_args(args_factory, tmp_path,
                                            name="iron_condor"))

    assert result["friction_verdict"] in ("thin", "untradeable")
    assert any("friction verdict" in note for note in result["notes"])


def test_snapshot_degradation_is_inherited(chain_snapshot, args_factory,
                                           tmp_path):
    """Catches a plan looking clean while its inputs were not.

    A consumer reading only the plan would otherwise never learn that the
    chain it was built from was degraded.
    """
    put_snapshot(chain_snapshot, tmp_path, degraded=True,
                 degraded_reason="engine missing when the chain was pulled")
    result = strategy_cmd.run(strategy_args(args_factory, tmp_path,
                                            name="straddle"))

    meta = read_json(result["artifact"])["meta"]
    assert meta["degraded"] is True
    assert "engine missing" in meta["degraded_reason"]


def test_snapshot_notes_are_carried_without_becoming_degradation(
        chain_snapshot, args_factory, tmp_path):
    """Catches an observation being promoted into a quality warning.

    Wing contracts with no quotes are what a real chain looks like. If that
    note degraded the plan, every plan would be degraded.
    """
    put_snapshot(chain_snapshot, tmp_path,
                 notes=["4 of 18 contracts have no usable implied volatility"])
    result = strategy_cmd.run(strategy_args(args_factory, tmp_path,
                                            name="straddle"))

    meta = read_json(result["artifact"])["meta"]
    assert meta["degraded"] is False
    assert meta["degraded_reason"] is None
    assert any("no usable implied volatility" in note
               for note in meta["notes"])


def test_list_needs_no_snapshot(args_factory, tmp_path):
    """Catches --list acquiring a dependency on artifacts on disk.

    The playbook is a property of the engine, not of any chain, and it has
    to be readable before anything has been pulled.
    """
    result = strategy_cmd.run(strategy_args(args_factory, tmp_path,
                                            list_only=True))
    names = [entry["name"] for entry in result["strategies"]]

    assert "iron_condor" in names
    assert names == sorted(names)
    # Structures needing two expiries are declared, not silently omitted,
    # and since the time-spread engine landed they are buildable too, from
    # a second chain rather than from this one.
    calendar = next(e for e in result["strategies"]
                    if e["name"] == "calendar_spread")
    assert calendar["needs_two_expiries"] is True
    assert calendar["buildable"] is True


def test_recommend_ranks_for_an_outlook(args_factory, tmp_path):
    """Catches the ranking losing its order or its stated caveat.

    The ranking matches a structure to a view; presenting it without the
    caveat would read as a recommendation to trade.
    """
    result = strategy_cmd.run(strategy_args(args_factory, tmp_path,
                                            recommend="2"))
    scores = [row["score"] for row in result["ranked"]]

    assert result["outlook"] == 2
    assert scores == sorted(scores, reverse=True)
    assert result["ranked"][0]["strategy"] == "long_call"
    assert "not a recommendation" in result["note"]


def test_unknown_strategy_names_the_known_ones(chain_snapshot, args_factory,
                                               tmp_path):
    """Catches an unknown name failing without telling the user what exists.

    The error a user actually sees has to be one they can act on.
    """
    put_snapshot(chain_snapshot, tmp_path)
    with pytest.raises(KeyError) as excinfo:
        strategy_cmd.run(strategy_args(args_factory, tmp_path,
                                       name="no_such_strategy"))
    message = str(excinfo.value)
    assert "no_such_strategy" in message and "iron_condor" in message


def test_a_two_expiry_structure_says_what_it_needs(
        chain_snapshot, args_factory, tmp_path):
    """Catches a calendar being built from a single expiry.

    A calendar cannot be expressed with one expiry, and returning something
    anyway would be a plan for a trade that is not the one named. Since the
    time-spread engine landed the refusal is actionable rather than flat:
    it names the command that would supply the missing chain.
    """
    put_snapshot(chain_snapshot, tmp_path)
    with pytest.raises(FileNotFoundError) as excinfo:
        strategy_cmd.run(strategy_args(args_factory, tmp_path,
                                       name="calendar_spread"))
    message = str(excinfo.value)
    assert "spans two expiries" in message
    assert "optiondesk chain" in message


def test_a_calendar_builds_once_a_later_chain_exists(
        chain_snapshot, args_factory, tmp_path):
    """The other half of the contract: given both chains, it builds.

    The near leg must be the one that expires first, and the far leg must
    still carry time value at the near expiry, which is the entire
    mechanism of the structure.
    """
    import copy

    near = put_snapshot(chain_snapshot, tmp_path)
    far = copy.deepcopy(near)
    far["expiry"] = "2026-10-16"
    far["days_to_expiry"] = near["days_to_expiry"] + 28
    from optiondesk.artifacts import write_json

    write_json(far, "chain_TEST_2026-10-16.json", tmp_path)

    result = strategy_cmd.run(strategy_args(args_factory, tmp_path,
                                            name="calendar_spread"))
    assert result["built"] is True
    assert result["far_days"] > result["near_days"]
    assert len(result["legs"]) == 2
    short = [leg for leg in result["legs"] if leg["side"] == "short"][0]
    long_leg = [leg for leg in result["legs"] if leg["side"] == "long"][0]
    assert short["days_to_expiry"] < long_leg["days_to_expiry"]
    assert short["strike"] == long_leg["strike"]
    assert "two volatilities" in result["assumption"]


def test_missing_snapshot_is_an_actionable_error(args_factory, tmp_path):
    """Catches an empty artifact directory producing an opaque failure.

    The message has to name the command that fixes it.
    """
    with pytest.raises(FileNotFoundError) as excinfo:
        strategy_cmd.run(strategy_args(args_factory, tmp_path,
                                       name="iron_condor"))
    assert "optiondesk chain" in str(excinfo.value)


def test_no_name_and_no_mode_is_refused(args_factory, tmp_path):
    """Catches a nameless invocation silently building something arbitrary."""
    with pytest.raises(ValueError) as excinfo:
        strategy_cmd.run(strategy_args(args_factory, tmp_path))
    assert "--list" in str(excinfo.value)


def test_curve_bounds_cover_spot_and_every_strike():
    """Catches a payoff window that crops the structure out of the picture.

    A curve drawn tighter than the strikes hides the part of the graph the
    reader opened it for.
    """
    lo, hi = strategy_cmd._curve_bounds(100.0, None, [70.0, 130.0])
    assert lo < 70.0 and hi > 130.0
    assert lo > 0
    # With no strikes and no band it still spans a usable region around spot.
    lo, hi = strategy_cmd._curve_bounds(100.0, None, [])
    assert lo == pytest.approx(75.0)
    assert hi == pytest.approx(125.0)
    # A wide expected move widens the window rather than being ignored.
    wide_lo, wide_hi = strategy_cmd._curve_bounds(100.0, (40.0, 160.0), [])
    assert wide_hi - wide_lo > hi - lo


def test_curve_bounds_never_go_below_zero():
    """Catches a negative underlying price entering the payoff curve.

    A price axis that runs through zero puts the model somewhere it cannot
    be evaluated.
    """
    lo, _ = strategy_cmd._curve_bounds(1.0, (0.0, 500.0), [500.0])
    assert lo > 0


def test_the_published_curve_agrees_with_its_own_analysis(
        chain_snapshot, args_factory, tmp_path):
    """One artifact carried two prices for the same structure.

    payoff_curve takes r and q after points, and the call passed five
    positional arguments, so the curve was drawn at the module defaults of
    4 percent and no dividend while the analysis beside it used the rates
    the snapshot measured. A calendar reported max_gain 8.136160 in a file
    whose own curve peaked at 9.030645 at the same underlying price, with
    both fields declaring the same rate: 11 percent of the maximum gain,
    6.9 percent of the capital at risk.
    """
    import copy
    from optiondesk.artifacts import read_json, write_json

    # A rate that differs from the module default, or the two paths agree
    # by luck and this test proves nothing. The shared fixture carries
    # 0.04, which is exactly the default the curve used to be drawn at.
    near = chain_snapshot()
    near["risk_free_rate"] = 0.01
    near["dividend_yield"] = 0.03
    write_json(near, "chain_TEST_2026-09-18.json", tmp_path)
    far = copy.deepcopy(near)
    far["expiry"] = "2026-10-16"
    far["days_to_expiry"] = near["days_to_expiry"] + 28
    write_json(far, "chain_TEST_2026-10-16.json", tmp_path)

    result = strategy_cmd.run(strategy_args(args_factory, tmp_path,
                                            name="calendar_spread"))
    assert result["built"] is True
    plan = read_json(result["artifact"])
    assert plan["risk_free_rate"] == 0.01
    peak = max(plan["payoff_curve"]["pnl"])
    assert abs(peak - plan["analysis"]["max_gain"]) < 1e-9, (
        "the curve peaks at {} while the analysis says {}".format(
            peak, plan["analysis"]["max_gain"]))
    assert plan["risk_free_rate"] is not None


def _two_expiries(chain_snapshot, tmp_path, **far_overrides):
    """A near chain and a far chain priced at its own 58 days.

    The tests above copy the near chain and relabel it, which is enough
    to prove a calendar builds. It is not enough here: a far leg quoted at
    the near leg's price makes the calendar free, so it cannot lose, its
    probability of profit is exactly one and its friction has no premium
    to compare against.
    """
    near = put_snapshot(chain_snapshot, tmp_path)
    far = put_snapshot(chain_snapshot, tmp_path, expiry="2026-10-16",
                       days=near["days_to_expiry"] + 28, **far_overrides)
    return near, far


@pytest.mark.parametrize("name,theta_sign", [
    # Short the front against one back-month contract: collects decay.
    ("calendar_spread", 1),
    ("diagonal_spread", 1),
    # Two back-month longs against one front short: pays decay, and the
    # ratio is the point of the structure rather than a mistake.
    ("ratio_call_diagonal", -1),
])
def test_a_time_spread_plan_carries_greeks_probability_and_friction(
        chain_snapshot, args_factory, tmp_path, name, theta_sign):
    """Two-expiry plans were written with all three null while the schema,
    docs/CAPABILITIES.md and the strategy skill said every plan carries
    them. The Greeks are checked against an independent sum over the legs
    at each leg's own expiry, which is the part that has to be right: at
    one expiry and one volatility a calendar's legs cancel exactly.
    """
    from optiondesk import engine_bridge

    _two_expiries(chain_snapshot, tmp_path)
    result = strategy_cmd.run(strategy_args(args_factory, tmp_path,
                                            name=name))
    assert result["built"] is True
    plan = read_json(result["artifact"])
    assert validate(plan, SCHEMA_FILES[STRATEGY_PLAN]) is plan

    all_greeks = engine_bridge.require()["all_greeks"]
    expected = {key: 0.0 for key in ("delta", "gamma", "vega", "theta",
                                     "rho")}
    for leg in plan["legs"]:
        greeks = all_greeks(plan["spot"], leg["strike"],
                            leg["days_to_expiry"] / 365.0, leg["iv"],
                            leg["kind"], plan["risk_free_rate"],
                            plan["dividend_yield"])
        side = 1 if leg["side"] == "long" else -1
        for key in expected:
            expected[key] += side * leg["qty"] * greeks[key]
    net = plan["net_greeks"]
    for key, value in expected.items():
        assert net[key] == pytest.approx(value, abs=1e-9), key
    assert net["complete"] is True
    assert net["legs_priced"] == 2
    # Long the back month against the front is long vega whatever the
    # ratio; on this fixture both chains carry the same volatility at a
    # strike, so at one expiry the calendar's vega would be exactly zero.
    assert net["vega"] > 1.0
    assert net["theta"] * theta_sign > 0

    probability = plan["probability"]
    assert 0.0 < probability["profit"] < 1.0
    assert probability["profit"] + probability["loss"] == pytest.approx(
        1.0, abs=1e-6)
    assert probability["expected_loss"] < 0
    assert "near expiry" in probability["model"]

    friction = plan["friction"]
    assert friction["verdict"] in ("ok", "thin", "untradeable")
    assert friction["round_trip"] > 0
    assert friction["legs_without_quotes"] == 0

    assert result["probability_of_profit"] == probability["profit"]
    assert result["expected_pnl"] == probability["expected_pnl"]
    assert result["net_vega"] == net["vega"]
    assert result["net_theta"] == net["theta"]
    assert result["friction_verdict"] == friction["verdict"]
    assert any("integrated cell by cell" in note
               for note in plan["meta"]["notes"])


def test_a_time_spread_without_an_atm_volatility_still_carries_greeks(
        chain_snapshot, args_factory, tmp_path):
    """The probability needs the near chain's at-the-money volatility and
    is withheld without it. The Greeks and the friction need only the legs
    and must not vanish with it."""
    from conftest import STRIKES

    # Every call on both chains without a volatility: chain_iv reads the
    # call nearest spot, so the put calendar has legs to mark and no law
    # to integrate against.
    no_iv = {(strike, "call") for strike in STRIKES}
    near = put_snapshot(chain_snapshot, tmp_path, no_iv=no_iv)
    put_snapshot(chain_snapshot, tmp_path, expiry="2026-10-16",
                 days=near["days_to_expiry"] + 28, no_iv=no_iv)

    result = strategy_cmd.run(strategy_args(args_factory, tmp_path,
                                            name="calendar_put_spread"))
    assert result["built"] is True
    plan = read_json(result["artifact"])
    assert plan["probability"] is None
    assert plan["net_greeks"]["legs_priced"] == 2
    assert plan["friction"]["verdict"] in ("ok", "thin", "untradeable")
    assert result["probability_of_profit"] is None
    assert result["net_vega"] > 0
