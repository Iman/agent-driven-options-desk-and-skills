"""optiondesk simulate: wiring, convergence honesty, and saved structures.

The posterior is fitted with a deliberately tiny draw count. That is enough
to exercise every branch this module owns and it keeps the suite fast; the
sampler itself is the engine's to test.
"""

import json

import pytest

from optiondesk.artifacts import read_json, write_json
from optiondesk.cli import simulate as simulate_cmd
from optiondesk.contracts import SCHEMA_FILES, SIMULATION, validate
from optiondesk.providers.base import ProviderDataError

from marks import needs_engine

TINY = {"horizon": 3, "paths": 200, "draws": 40, "burn": 20, "chains": 2}


def simulate_args(args_factory, tmp_path, **overrides):
    kwargs = {"symbol": "TEST", "period": "2y", "provider": None,
              "no_structures": True, "out_dir": str(tmp_path)}
    kwargs.update(TINY)
    kwargs.update(overrides)
    return args_factory(**kwargs)


@needs_engine
def test_simulation_artifact_validates_and_records_its_settings(
        stub_provider, log_returns, args_factory, tmp_path):
    """Catches a simulation payload that no longer satisfies simulation/v1.

    The dashboard reads this artifact, and the inputs block is the only
    record of the draw and path counts a quantile was produced with.
    """
    stub_provider(history=log_returns)
    result = simulate_cmd.run(simulate_args(args_factory, tmp_path))

    payload = read_json(result["artifact"])
    assert payload["meta"]["schema"] == SIMULATION
    assert validate(payload, SCHEMA_FILES[SIMULATION]) is payload
    assert payload["meta"]["inputs"]["draws"] == 40
    assert payload["meta"]["inputs"]["paths"] == 200
    assert payload["simulation"]["requested_paths"] == 200
    assert payload["simulation"]["horizon_days"] == 3
    assert len(payload["simulation"]["fan"]) == 3
    assert payload["underlying"] == "TEST"


@needs_engine
def test_a_sampler_that_has_not_converged_degrades_the_artifact(
        stub_provider, log_returns, args_factory, tmp_path):
    """Catches unconverged quantiles being published as though trustworthy.

    Forty draws cannot converge. The quantiles are still written, and the
    artifact has to say plainly that they should not be quoted.
    """
    stub_provider(history=log_returns)
    result = simulate_cmd.run(simulate_args(args_factory, tmp_path))
    payload = read_json(result["artifact"])

    assert result["converged"] is False
    assert payload["posterior"]["converged"] is False
    assert payload["meta"]["degraded"] is True
    assert "has not converged" in payload["meta"]["degraded_reason"]
    # The quantiles are present regardless, so a reader can see them.
    assert payload["simulation"]["fan"][-1]["p50"] > 0


@needs_engine
def test_the_fan_is_ordered_and_the_terminal_histogram_is_complete(
        stub_provider, log_returns, args_factory, tmp_path):
    """Catches quantiles being emitted out of order or paths being lost.

    A p5 above a p95 is a silently transposed label, and a histogram whose
    counts do not add up to the path count has dropped outcomes from a tail.
    """
    stub_provider(history=log_returns)
    result = simulate_cmd.run(simulate_args(args_factory, tmp_path))
    payload = read_json(result["artifact"])

    for row in payload["simulation"]["fan"]:
        assert row["p5"] <= row["p25"] <= row["p50"] <= row["p75"] <= row["p95"]
    counted = sum(b["count"] for b in
                  payload["simulation"]["terminal_histogram"])
    assert counted == payload["simulation"]["paths"] == 200


@needs_engine
def test_saved_plans_are_scored_against_realised_volatility(
        stub_provider, chain_snapshot, log_returns, args_factory, tmp_path):
    """Catches the second opinion silently repeating the first.

    The whole point is that these probabilities come from the volatility
    the underlying has shown, not the one the options are priced at. If the
    disagreement is never computed, the command has said nothing new.
    """
    stub_provider(history=log_returns)
    write_json({"strategy": "long_call", "expiry": "2026-09-18",
                "underlying": "TEST", "spot": 100.0,
                "probability": {"profit": 0.4},
                "legs": [{"kind": "call", "side": "long", "price": 3.59,
                          "strike": 100.0, "qty": 1.0}]},
               "strategy_TEST_long_call_2026-09-18.json", tmp_path)

    result = simulate_cmd.run(simulate_args(args_factory, tmp_path,
                                            no_structures=False))
    assert len(result["structures"]) == 1
    row = result["structures"][0]
    assert row["strategy"] == "long_call"
    assert row["implied"] == 0.4
    assert 0.0 <= row["realised"] <= 1.0
    assert row["disagreement"] == pytest.approx(row["realised"] - 0.4)
    assert any("realised" in note and "implied" in note
               for note in result["notes"])


@needs_engine
def test_no_structures_reads_no_plans(stub_provider, log_returns,
                                      args_factory, tmp_path):
    """Catches the flag having no effect, which would make it a lie.

    It is the switch that keeps the command fast when only the fan is
    wanted.
    """
    stub_provider(history=log_returns)
    write_json({"strategy": "long_call", "expiry": "2026-09-18",
                "underlying": "TEST", "spot": 100.0,
                "legs": [{"kind": "call", "side": "long", "price": 3.59,
                          "strike": 100.0, "qty": 1.0}]},
               "strategy_TEST_long_call_2026-09-18.json", tmp_path)

    result = simulate_cmd.run(simulate_args(args_factory, tmp_path,
                                            no_structures=True))
    assert result["structures"] == []
    assert result["notes"] == []


@needs_engine
def test_an_unreadable_plan_is_skipped_not_fatal(stub_provider, log_returns,
                                                 args_factory, tmp_path):
    """Catches one corrupt plan stopping the simulation of every other one."""
    stub_provider(history=log_returns)
    (tmp_path / "strategy_TEST_broken_2026-09-18.json").write_text(
        "{not json", encoding="utf-8")
    write_json({"strategy": "long_call", "expiry": "2026-09-18",
                "underlying": "TEST", "spot": 100.0,
                "legs": [{"kind": "call", "side": "long", "price": 3.59,
                          "strike": 100.0, "qty": 1.0}]},
               "strategy_TEST_long_call_2026-09-18.json", tmp_path)

    result = simulate_cmd.run(simulate_args(args_factory, tmp_path,
                                            no_structures=False))
    assert [row["strategy"] for row in result["structures"]] == ["long_call"]


@needs_engine
def test_plans_for_another_underlying_are_not_scored(
        stub_provider, log_returns, args_factory, tmp_path):
    """Catches one symbol's structures being priced off another's paths.

    The glob is the only thing keeping them apart, and a widened one would
    report a QQQ condor under a SPY simulation.
    """
    stub_provider(history=log_returns)
    write_json({"strategy": "long_call", "expiry": "2026-09-18",
                "underlying": "OTHER", "spot": 100.0,
                "legs": [{"kind": "call", "side": "long", "price": 3.59,
                          "strike": 100.0, "qty": 1.0}]},
               "strategy_OTHER_long_call_2026-09-18.json", tmp_path)

    result = simulate_cmd.run(simulate_args(args_factory, tmp_path,
                                            no_structures=False))
    assert result["structures"] == []


@needs_engine
def test_a_provider_that_raises_is_not_swallowed(stub_provider, args_factory,
                                                 tmp_path):
    """Catches a history failure producing a simulation of nothing."""
    stub_provider(raises=ProviderDataError(
        "TEST: only 12 closes available, too few to estimate a volatility "
        "model"))
    with pytest.raises(ProviderDataError) as excinfo:
        simulate_cmd.run(simulate_args(args_factory, tmp_path))
    assert "too few" in str(excinfo.value)


# ------------------------------------------------------------- _histogram

def test_histogram_places_every_value_in_exactly_one_bin():
    """Catches values being dropped or double counted at a bin edge.

    The top value sits exactly on the last upper edge, which is the index
    that overflows if the clamp is removed.
    """
    values = [float(v) for v in range(101)]
    bins = simulate_cmd._histogram(values, bins=10)

    assert len(bins) == 10
    assert sum(b["count"] for b in bins) == len(values)
    assert bins[0]["lo"] == 0.0
    assert bins[-1]["hi"] == pytest.approx(100.0)
    for lower, upper in zip(bins, bins[1:]):
        assert lower["hi"] == pytest.approx(upper["lo"])


def test_histogram_handles_a_degenerate_range():
    """Catches a division by zero when every path lands on the same price."""
    assert simulate_cmd._histogram([]) == []
    assert simulate_cmd._histogram([5.0, 5.0, 5.0]) == [
        {"lo": 5.0, "hi": 5.0, "count": 3}]


@needs_engine
def test_the_sampler_says_it_is_working_before_it_starts(
        stub_provider, log_returns, capsys, args_factory, tmp_path):
    """A run that prints nothing for minutes looks exactly like a hang.

    The sampler is pure Python and single threaded: it walks
    (draws + burn) x chains iterations over every observation with no
    vectorisation. On an eighteen core arm64 machine the default settings
    take about eight seconds and the heaviest sensible ones about
    twenty-seven, and a slower machine takes proportionally longer with no
    output and one busy core. Somebody will kill it and conclude the tool
    is broken.

    The notice goes to stderr, never stdout, because stdout is JSON that a
    caller parses.
    """
    stub_provider(history=log_returns)
    result = simulate_cmd.run(simulate_args(args_factory, tmp_path))
    captured = capsys.readouterr()

    assert "Let it run" in captured.err
    assert "single threaded" in captured.err
    assert "iterations over" in captured.err
    assert "Let it run" not in captured.out, (
        "the notice reached stdout, which a caller parses as JSON")
    assert result["artifact"]


def test_the_estimate_grows_with_the_work():
    """A fixed phrase would be worse than none: it would say a few seconds
    for a run that takes ten minutes. The estimate is linear in iterations
    times observations, from one measured constant, and deliberately vague
    above a minute because one machine's constant cannot carry more
    precision than that.
    """
    from optiondesk.cli.simulate import _rough_duration

    assert _rough_duration(8000, 1253) == "a few seconds"
    assert _rough_duration(32000, 1253) == "under a minute"
    assert _rough_duration(200000, 1253) == "a few minutes"
    assert _rough_duration(2000000, 5000) == "ten minutes or more"
