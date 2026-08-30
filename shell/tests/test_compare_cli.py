"""optiondesk compare: every structure from one chain, ranked together."""

import pytest

from optiondesk.artifacts import read_json, write_json
from optiondesk.cli import compare as compare_cmd
from optiondesk.contracts import SCHEMA_FILES, STRATEGY_COMPARISON, validate

from conftest import needs_engine

pytestmark = needs_engine


def compare_args(args_factory, tmp_path, **overrides):
    kwargs = {"snapshot": None, "size": 1.0, "include_underlying": False,
              "rebuild": False, "out_dir": str(tmp_path)}
    kwargs.update(overrides)
    return args_factory(**kwargs)


def put_snapshot(chain_snapshot, tmp_path, **overrides):
    snapshot = chain_snapshot(**overrides)
    write_json(snapshot, "chain_{}_{}.json".format(
        snapshot["underlying"], snapshot["expiry"]), tmp_path)
    return snapshot


def test_comparison_validates_and_carries_its_criterion_and_caveat(
        chain_snapshot, args_factory, tmp_path):
    """Catches the ordering being published without what produced it.

    A leader without the criterion is a recommendation. With the criterion
    and the caveat it is an ordering under stated assumptions, which is the
    only thing this command is entitled to produce.
    """
    put_snapshot(chain_snapshot, tmp_path)
    result = compare_cmd.run(compare_args(args_factory, tmp_path))

    payload = read_json(result["artifact"])
    assert payload["meta"]["schema"] == STRATEGY_COMPARISON
    assert validate(payload, SCHEMA_FILES[STRATEGY_COMPARISON]) is payload
    assert result["criterion"]
    assert "not a recommendation" in result["caveat"]
    assert result["compared"] >= 8
    assert result["rankable"] + result["excluded"] == result["compared"]


def test_the_ranking_is_ordered_and_the_leader_is_its_first_row(
        chain_snapshot, args_factory, tmp_path):
    """Catches the leader and the ordering disagreeing.

    A table sorted one way with a headline taken from another is how a
    reader ends up quoting a structure the table does not put first.
    """
    put_snapshot(chain_snapshot, tmp_path)
    result = compare_cmd.run(compare_args(args_factory, tmp_path))
    payload = read_json(result["artifact"])

    ranked = [row for row in payload["rows"] if row.get("rankable")]
    ranked.sort(key=lambda row: row["rank"])
    assert ranked[0]["strategy"] == payload["leader"]["strategy"]
    assert result["leader"]["strategy"] == payload["leader"]["strategy"]
    scores = [row["expected_return_on_risk"] for row in ranked]
    assert scores == sorted(scores, reverse=True)


def test_structures_needing_a_holding_are_declared_not_dropped(
        chain_snapshot, args_factory, tmp_path):
    """Catches a structure vanishing from the comparison with no reason.

    A silently missing row reads as a structure that was considered and
    lost, which is a different claim from one that was never eligible.
    """
    put_snapshot(chain_snapshot, tmp_path)
    without = compare_cmd.run(compare_args(args_factory, tmp_path))
    excluded = {entry["strategy"]: entry["reason"]
                for entry in without["not_compared"]}

    assert "covered_call" in excluded
    assert "--include-underlying" in excluded["covered_call"]
    assert "calendar_spread" in excluded
    assert "two expiries" in excluded["calendar_spread"]
    # Each refusal is also visible on the artifact itself.
    notes = read_json(without["artifact"])["meta"]["notes"]
    assert any("covered_call not compared" in note for note in notes)


def test_include_underlying_brings_the_holding_structures_in(
        chain_snapshot, args_factory, tmp_path):
    """Catches the flag having no effect on what is compared."""
    put_snapshot(chain_snapshot, tmp_path)
    without = compare_cmd.run(compare_args(args_factory, tmp_path))
    with_holding = compare_cmd.run(compare_args(args_factory, tmp_path,
                                                include_underlying=True))

    assert with_holding["compared"] > without["compared"]
    strategies = {row["strategy"]
                  for row in read_json(with_holding["artifact"])["rows"]}
    assert "covered_call" in strategies


def test_every_compared_structure_comes_from_the_named_snapshot(
        chain_snapshot, args_factory, tmp_path):
    """Catches plans from another expiry being folded into the comparison.

    The plans are rebuilt from one snapshot on purpose. Reading whatever
    plan files happen to be on disk would compare a September structure
    against an October one and call it a ranking.
    """
    put_snapshot(chain_snapshot, tmp_path, expiry="2026-09-18")
    october = chain_snapshot(expiry="2026-10-16")
    write_json(october, "chain_TEST_2026-10-16.json", tmp_path)
    wanted = tmp_path / "chain_TEST_2026-09-18.json"

    result = compare_cmd.run(compare_args(args_factory, tmp_path,
                                          snapshot=str(wanted)))
    payload = read_json(result["artifact"])
    assert payload["expiry"] == "2026-09-18"
    for name in {row["strategy"] for row in payload["rows"]}:
        plan = read_json(tmp_path / "strategy_TEST_{}_2026-09-18.json".format(
            name))
        assert plan["expiry"] == "2026-09-18"


def test_missing_snapshot_is_an_actionable_error(args_factory, tmp_path):
    """Catches an empty artifact directory producing an opaque failure."""
    with pytest.raises(FileNotFoundError) as excinfo:
        compare_cmd.run(compare_args(args_factory, tmp_path))
    assert "optiondesk chain" in str(excinfo.value)


def test_a_structure_the_chain_cannot_form_is_reported_with_a_reason(
        chain_snapshot, args_factory, tmp_path):
    """Catches an unbuildable structure aborting the whole comparison.

    A chain listing one strike cannot form a spread. That is an answer
    about the chain, and it has to arrive as a row with a reason rather
    than as a failure of the command.
    """
    put_snapshot(chain_snapshot, tmp_path, strikes=(100.0,))
    result = compare_cmd.run(compare_args(args_factory, tmp_path))
    reasons = {entry["strategy"]: entry["reason"]
               for entry in result["not_compared"]}

    assert result["compared"] >= 1
    assert "no viable structure" in reasons["iron_condor"]
    assert "another expiry" in reasons["iron_condor"]
